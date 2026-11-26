"""Keeps already-published files consistent with the permanent student-protection rule (``bot/policy.py``).

Telegram cannot change ``protect_content`` on an existing message, so files whose stored ``protect_requested``
differs from the current policy are re-posted (silently) with the right flag, the new message id is stored, and
the old message goes through the cleanup queue. Each new post is *held* in the queue before being referenced, so a
crash or a concurrent approval/deletion can never orphan it.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bot import texts
from bot.db import repositories as repo
from bot.db.database import Database
from bot.models import DELETABLE
from bot.policy import protect_for_stage
from bot.services.cleanup import CleanupService
from bot.services.telegram_gateway import TelegramGateway

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    updated: int
    failed: int
    remaining: int


class ProtectionService:
    def __init__(self, db: Database, gateway: TelegramGateway, cleanup: CleanupService, batch_size: int = 25) -> None:
        self.db = db
        self.gw = gateway
        self.cleanup = cleanup
        self.batch_size = batch_size
        self._lock = asyncio.Lock()

    async def stats(self) -> dict:
        """Verification counters (flag reported by Telegram) and how many files still differ from the rule."""
        async with self.db.read() as c:
            return await repo.protection_stats(c, protect_for_stage("temp"), protect_for_stage("approved"))

    async def sync(self, limit: int | None = None) -> SyncResult | None:
        """Re-publish outdated files. Returns None if another sync is already running."""
        if self._lock.locked():
            return None
        async with self._lock:
            async with self.db.read() as c:
                files = await repo.files_needing_protection_sync(c, protect_for_stage("temp"),
                                                                 protect_for_stage("approved"),
                                                                 limit or self.batch_size)
            updated = failed = 0
            for f in files:
                desired = protect_for_stage(f.stage)
                async with self.db.read() as c:
                    content = await repo.get_content(c, f.content_id)
                if content is None:
                    continue
                try:
                    sent = await self.gw.send_document(f.chat_id, f.file_id,
                                                       texts.channel_caption(content, approved=f.stage == "approved"),
                                                       desired, silent=True)
                except Exception as exc:
                    failed += 1
                    log.warning("protection_sync_failed", extra={"ctx": {"content": f.content_id, "kind": f.kind,
                                                                         "error": str(exc)}})
                    continue
                await self.cleanup.hold(None, f.chat_id, sent.message_id, "protection_resync")
                async with self.db.tx() as c:
                    current = await repo.get_file(c, f.content_id, f.kind)
                    status = await repo.get_status(c, f.content_id)
                    unchanged = (current is not None and current.chat_id == f.chat_id
                                 and current.message_id == f.message_id and status in DELETABLE)
                    if unchanged:
                        await repo.replace_file_message(c, f.content_id, f.kind, sent.message_id, desired, sent.protected)
                        await repo.enqueue(c, f.chat_id, f.message_id, "protection_resync", content_ref=f.content_id)
                        await repo.release_hold(c, f.chat_id, sent.message_id)
                    else:  # content changed meanwhile (approved/deleted/resubmitted): discard the new post
                        await repo.activate_hold(c, f.chat_id, sent.message_id, "protection_resync_discarded")
                if unchanged:
                    updated += 1
            remaining = (await self.stats())["outdated"]
        await self.cleanup.process_due()
        log.info("protection_sync", extra={"ctx": {"updated": updated, "failed": failed, "remaining": remaining}})
        return SyncResult(updated, failed, remaining)

    async def sync_tick(self) -> None:
        """Called by the background worker on every tick: re-publish files that do not follow the rule yet
        (posted before the rule existed, or a previous attempt failed). A no-op once everything is consistent."""
        if (await self.stats())["outdated"]:
            await self.sync()
