"""Database-backed cleanup queue, deletion jobs, preview expiry and crash recovery."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from bot.db import repositories as repo
from bot.db.database import Database, utc_offset
from bot.models import DeletionReport, QueueItem, Role, Status
from bot.permissions import require_role
from bot.services.notifier import Notifier, NullNotifier
from bot.services.telegram_gateway import DeleteResult, TelegramGateway

log = logging.getLogger(__name__)


class CleanupService:
    def __init__(self, db: Database, gateway: TelegramGateway, *, max_attempts: int, preview_ttl_hours: int,
                 stale_minutes: int, notifier: Notifier | None = None) -> None:
        self.db = db
        self.gw = gateway
        self.max_attempts = max_attempts
        self.preview_ttl_hours = preview_ttl_hours
        self.stale_minutes = stale_minutes
        self.notifier: Notifier = notifier or NullNotifier()
        self._process_lock = asyncio.Lock()
        # extra maintenance steps run on every tick (e.g. protection re-publishing)
        self.periodic: list[Callable[[], Awaitable[None]]] = []

    # ── staging ──
    async def hold(self, content_id: int | None, chat_id: int, message_id: int, reason: str) -> None:
        """Track a message posted during an in-flight operation, *before* it is referenced elsewhere."""
        async with self.db.tx() as c:
            await repo.enqueue(c, chat_id, message_id, reason, content_ref=content_id, status="held")

    # ── processing ──
    async def _process(self, items: list[QueueItem]) -> None:
        for item in items:
            result, err = await self.gw.delete(item.chat_id, item.message_id)
            async with self.db.tx() as c:
                if result is DeleteResult.FAILED:
                    await repo.mark_item_retry(c, item.id, err or "unknown", self.max_attempts)
                else:
                    await repo.mark_item_done(c, item.id, err if result is DeleteResult.GONE else None)
            log.info("cleanup_item", extra={"ctx": {"item": item.id, "chat_id": item.chat_id,
                                                    "message_id": item.message_id, "result": result.value,
                                                    "reason": item.reason, "error": err}})

    async def process_due(self, limit: int = 100) -> int:
        async with self._process_lock:
            async with self.db.read() as c:
                items = await repo.due_items(c, limit)
            await self._process(items)
            return len(items)

    async def process_job(self, job_id: int) -> DeletionReport:
        async with self._process_lock:
            async with self.db.read() as c:
                items = await repo.job_open_items(c, job_id)
            await self._process(items)
        return await self._finalize_job(job_id, notify_completion=False)

    async def _finalize_job(self, job_id: int, notify_completion: bool) -> DeletionReport:
        async with self.db.tx() as c:
            job = await repo.get_job(c, job_id)
            counts = await repo.job_counts(c, job_id)
            open_count = counts["pending"] + counts["held"]
            if open_count == 0 and counts["failed"] == 0:
                status = "completed"
            elif open_count == 0:
                status = "needs_attention"
            else:
                status = "in_progress"
            should_notify = notify_completion and status != "in_progress" and job["notified_status"] != status
            # When reported synchronously to the admin, mark completion as already notified.
            notified = status if (should_notify or (not notify_completion and status == "completed")) else None
            await repo.set_job_status(c, job_id, status, notified)
        if should_notify and job["requested_by"]:
            await self.notifier.job_finished(job["requested_by"], job_id, job["description"], counts, status)
        total = sum(counts.values())
        return DeletionReport(job_id, job["description"], total, counts["done"], open_count, counts["failed"])

    async def finalize_jobs(self) -> None:
        async with self.db.read() as c:
            jobs = await repo.open_jobs(c)
        for job in jobs:
            await self._finalize_job(job["id"], notify_completion=True)

    async def expire_previews(self) -> int:
        cutoff = utc_offset(hours=-self.preview_ttl_hours)
        async with self.db.tx() as c:
            rows = await repo.expired_previews(c, cutoff)
            for r in rows:
                await repo.enqueue(c, r["chat_id"], r["message_id"], "preview_expired", content_ref=r["content_id"])
            await repo.delete_preview_ids(c, [r["id"] for r in rows])
        return len(rows)

    async def recover(self, stale_only: bool) -> int:
        """Roll back operations interrupted by a crash or a hung API call."""
        cutoff = utc_offset(minutes=-self.stale_minutes) if stale_only else None
        rolled: list[tuple[int, int | None, str]] = []
        async with self.db.tx() as c:
            for row in await repo.transitional_contents(c, cutoff):
                cid, status = row["id"], row["status"]
                await repo.activate_holds(c, cid, "rollback_" + status)
                if status == Status.UPLOADING.value:
                    await repo.delete_content_row(c, cid)
                elif status == Status.RESUBMITTING.value:
                    await repo.transition(c, cid, status, Status.REJECTED.value)
                else:  # approving
                    await repo.transition(c, cid, status, Status.PENDING.value)
                rolled.append((cid, row["student_id"], status))
            await repo.activate_orphan_holds(c, utc_offset(minutes=-self.stale_minutes))
        for cid, student_id, status in rolled:
            log.warning("operation_rolled_back", extra={"ctx": {"content": cid, "status": status}})
            if student_id and status != Status.APPROVING.value:
                await self.notifier.operation_rolled_back(student_id, cid, status)
        return len(rolled)

    async def tick(self) -> None:
        await self.recover(stale_only=True)
        await self.expire_previews()
        await self.process_due()
        await self.finalize_jobs()
        async with self.db.tx() as c:
            await repo.purge_done(c, utc_offset(days=-30))
        for step in self.periodic:
            try:
                await step()
            except Exception:
                log.exception("periodic_step_failed")

    async def run_forever(self, interval: int, stop: asyncio.Event) -> None:
        log.info("cleanup_worker_started", extra={"ctx": {"interval": interval}})
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("cleanup_tick_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    # ── admin views ──
    async def stats(self) -> dict:
        async with self.db.read() as c:
            return await repo.queue_stats(c)

    async def failed_items(self, limit: int = 10):
        async with self.db.read() as c:
            return await repo.failed_items(c, limit)

    async def retry_failed(self, actor_id: int) -> int:
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            n = await repo.retry_failed(c)
        await self.process_due()
        await self.finalize_jobs()
        return n
