"""Content lifecycle: submission, resubmission, review (approve/reject), previews and deletion."""
from __future__ import annotations

import logging
import sqlite3

from bot import texts
from bot.config import Channels
from bot.db import repositories as repo
from bot.db.database import Database, utcnow
from bot.models import (
    DELETABLE, TRANSITIONAL, Content, ContentType, DeletionReport, FileInfo, Role, Sent, Status, Subject,
)
from bot.policy import protect_for_role, protect_for_stage
from bot.permissions import REVIEWERS, require_role
from bot.services import validators as v
from bot.services.cleanup import CleanupService
from bot.services.errors import DomainError
from bot.services.notifier import Notifier, NullNotifier
from bot.services.telegram_gateway import TelegramGateway

log = logging.getLogger(__name__)
CONTENT_TYPES = {t.value for t in ContentType}


class ApprovedCounts:
    """Lookup of approved totals: y=year, sp=specialization, sm=(year, spec|0, semester), sb=subject, t=(subject, type)."""

    def __init__(self) -> None:
        self.data: dict[tuple, int] = {}

    def year(self, year_id: int) -> int:
        return self.data.get(("y", year_id), 0)

    def spec(self, spec_id: int) -> int:
        return self.data.get(("sp", spec_id), 0)

    def semester(self, year_id: int, spec_id: int | None, semester: int) -> int:
        return self.data.get(("sm", year_id, spec_id or 0, semester), 0)

    def subject(self, subject_id: int) -> int:
        return self.data.get(("sb", subject_id), 0)

    def type(self, subject_id: int, ctype: str) -> int:
        return self.data.get(("t", subject_id, ctype), 0)


class ContentService:
    def __init__(self, db: Database, gateway: TelegramGateway, channels: Channels,
                 cleanup: CleanupService, notifier: Notifier | None = None) -> None:
        self.db = db
        self.gw = gateway
        self.channels = channels
        self.cleanup = cleanup
        self.notifier: Notifier = notifier or NullNotifier()

    # ───────────── queries ─────────────
    async def get(self, content_id: int) -> Content:
        async with self.db.read() as c:
            content = await repo.get_content(c, content_id)
        if not content:
            raise DomainError("content_not_found")
        return content

    async def get_for_student(self, student_id: int, content_id: int) -> Content:
        content = await self.get(content_id)
        if content.student_id != student_id:
            raise DomainError("content_not_found")
        return content

    async def number_taken(self, subject_id: int, ctype: str, number: int) -> bool:
        async with self.db.read() as c:
            return await repo.content_exists(c, subject_id, ctype, number)

    async def assigned_subject(self, student_id: int, subject_id: int) -> Subject:
        async with self.db.read() as c:
            if not await repo.is_assigned(c, student_id, subject_id):
                raise DomainError("subject_not_assigned")
            return await repo.get_subject(c, subject_id)

    async def pending(self, page: int, per: int) -> tuple[list[Content], int]:
        async with self.db.read() as c:
            return await repo.list_contents(c, status=Status.PENDING.value, order="c.submitted_at ASC",
                                            limit=per, offset=page * per)

    async def approved_counts(self) -> ApprovedCounts:
        """Approved totals at every level of the hierarchy (year → specialization → semester → subject → type)."""
        async with self.db.read() as c:
            rows = await repo.approved_counts(c)
        counts = ApprovedCounts()
        for r in rows:
            n = r["n"]
            spec = r["specialization_id"] or 0
            for key in (("y", r["year_id"]), ("sp", spec), ("sm", r["year_id"], spec, r["semester"]),
                        ("sb", r["subject_id"]), ("t", r["subject_id"], r["content_type"])):
                counts.data[key] = counts.data.get(key, 0) + n
        return counts

    async def approved_list(self, subject_id: int, ctype: str, page: int, per: int) -> tuple[list[Content], int]:
        async with self.db.read() as c:
            return await repo.list_contents(c, status=Status.APPROVED.value, subject_id=subject_id, ctype=ctype,
                                            order="c.content_type, c.number", limit=per, offset=page * per)

    async def number_statuses(self, subject_id: int, ctype: str) -> dict[int, str]:
        """Current occupation of content numbers for one subject + type (always read live from the DB)."""
        if ctype not in CONTENT_TYPES:
            raise DomainError("invalid_type")
        async with self.db.read() as c:
            return await repo.number_statuses(c, subject_id, ctype)

    async def student_recent(self, student_id: int, limit: int = 5) -> list[Content]:
        async with self.db.read() as c:
            items, _ = await repo.list_contents(c, student_id=student_id, order="c.submitted_at DESC", limit=limit)
        return items

    async def student_rejected(self, student_id: int, page: int, per: int) -> tuple[list[Content], int]:
        async with self.db.read() as c:
            return await repo.list_contents(c, status=Status.REJECTED.value, student_id=student_id,
                                            order="c.status_changed_at DESC", limit=per, offset=page * per)

    async def search(self, subject_id: int, ctype: str | None, number: int | None, page: int, per: int):
        async with self.db.read() as c:
            return await repo.list_contents(c, subject_id=subject_id, ctype=ctype, number=number,
                                            order="c.content_type, c.number", limit=per, offset=page * per)

    async def subject_summary(self, subject_id: int) -> dict[str, dict[str, list[int]]]:
        async with self.db.read() as c:
            rows = await repo.subject_number_summary(c, subject_id)
        out: dict[str, dict[str, list[int]]] = {}
        for r in rows:
            out.setdefault(r["content_type"], {}).setdefault(r["status"], []).append(r["number"])
        return out

    # ───────────── helpers ─────────────
    async def _post_files(self, content_id: int, caption: str, files: dict[str, FileInfo], reason: str
                          ) -> tuple[dict[str, Sent], bool]:
        """Post documents to the temp channels; every message is held in the queue right after posting."""
        protect = protect_for_stage("temp")
        posted: dict[str, Sent] = {}
        for kind, info in files.items():
            chat_id = self.channels.temp_for(kind)
            sent = await self.gw.send_document(chat_id, info.file_id, caption, protect)
            await self.cleanup.hold(content_id, chat_id, sent.message_id, reason)
            posted[kind] = sent
        return posted, protect

    async def _rollback(self, content_id: int, expected: str, back_to: str | None, reason: str) -> None:
        """Release a claimed operation: queue staged messages for deletion and restore the previous status."""
        async with self.db.tx() as c:
            await repo.activate_holds(c, content_id, reason)
            if back_to is None:
                await repo.delete_content_row(c, content_id)
            else:
                await repo.transition(c, content_id, expected, back_to)
        await self.cleanup.process_due()

    @staticmethod
    def _check_files(pdf: FileInfo | None, tex: FileInfo) -> None:
        if tex is None or not (tex.file_name or "").lower().endswith(".tex"):
            raise DomainError("invalid_tex")
        if pdf is not None and not pdf.file_id:
            raise DomainError("invalid_pdf")

    # ───────────── submission ─────────────
    async def submit(self, student_id: int, subject_id: int, ctype: str, number: int, pdf: FileInfo | None,
                     skip_reason: str | None, tex: FileInfo) -> Content:
        if ctype not in CONTENT_TYPES:
            raise DomainError("invalid_type")
        if not (1 <= number <= 9999):
            raise DomainError("invalid_number")
        self._check_files(pdf, tex)
        if pdf is None:
            skip_reason = v.clean_text(skip_reason, min_len=5, max_len=500, code="invalid_skip_reason")
        else:
            skip_reason = None

        # 1) reserve the number atomically (UNIQUE constraint is authoritative)
        async with self.db.tx() as c:
            await require_role(c, student_id, Role.STUDENT.value)
            if not await repo.is_assigned(c, student_id, subject_id):
                raise DomainError("subject_not_assigned")
            try:
                cid = await repo.insert_content(c, subject_id, ctype, number, student_id, skip_reason)
            except sqlite3.IntegrityError as exc:
                raise DomainError("duplicate_content") from exc
            draft = await repo.get_content(c, cid)

        # 2) post files (outside any transaction)
        files = {"pdf": pdf, "tex": tex} if pdf else {"tex": tex}
        try:
            posted, protect = await self._post_files(cid, texts.channel_caption(draft, approved=False), files,
                                                     "submit_failed")
        except Exception as exc:
            log.warning("submit_upload_failed", extra={"ctx": {"content": cid, "error": str(exc)}})
            await self._rollback(cid, Status.UPLOADING.value, None, "submit_failed")
            raise DomainError("upload_failed") from exc

        # 3) commit references + status
        async with self.db.tx() as c:
            if not await repo.transition(c, cid, Status.UPLOADING.value, Status.PENDING.value):
                await repo.activate_holds(c, cid, "submit_aborted")
                committed = False
            else:
                for kind, sent in posted.items():
                    info = files[kind]
                    await repo.upsert_file(c, cid, kind, "temp", self.channels.temp_for(kind), sent.message_id,
                                           info.file_id, info.file_unique_id, info.file_name, info.file_size,
                                           protect, sent.protected)
                await repo.release_holds(c, cid)
                committed = True
                content = await repo.get_content(c, cid)
                uploaders = await repo.user_ids_by_role(c, Role.UPLOADER.value)
        if not committed:
            raise DomainError("operation_interrupted")
        log.info("content_submitted", extra={"ctx": {"content": cid, "student": student_id}})
        await self.notifier.new_submission(content, uploaders, resubmitted=False)
        return content

    async def resubmit(self, student_id: int, content_id: int, pdf: FileInfo, tex: FileInfo) -> Content:
        if pdf is None:
            raise DomainError("pdf_required")
        self._check_files(pdf, tex)
        async with self.db.tx() as c:
            await require_role(c, student_id, Role.STUDENT.value)
            content = await repo.get_content(c, content_id)
            if not content or content.student_id != student_id:
                raise DomainError("content_not_found")
            if not await repo.transition(c, content_id, Status.REJECTED.value, Status.RESUBMITTING.value):
                raise DomainError("not_rejected")
        files = {"pdf": pdf, "tex": tex}
        try:
            posted, protect = await self._post_files(content_id, texts.channel_caption(content, approved=False),
                                                     files, "resubmit_failed")
        except Exception as exc:
            log.warning("resubmit_upload_failed", extra={"ctx": {"content": content_id, "error": str(exc)}})
            await self._rollback(content_id, Status.RESUBMITTING.value, Status.REJECTED.value, "resubmit_failed")
            raise DomainError("upload_failed") from exc

        async with self.db.tx() as c:
            ok = await repo.transition(c, content_id, Status.RESUBMITTING.value, Status.PENDING.value,
                                       pdf_skip_reason=None, submitted_at=utcnow())
            if not ok:
                await repo.activate_holds(c, content_id, "resubmit_aborted")
            else:
                await repo.release_holds(c, content_id)
                for old in await repo.get_files(c, content_id):
                    await repo.enqueue(c, old.chat_id, old.message_id, "replaced_by_resubmission",
                                       content_ref=content_id)
                for kind, sent in posted.items():
                    info = files[kind]
                    await repo.upsert_file(c, content_id, kind, "temp", self.channels.temp_for(kind), sent.message_id,
                                           info.file_id, info.file_unique_id, info.file_name, info.file_size,
                                           protect, sent.protected)
                content = await repo.get_content(c, content_id)
                uploaders = await repo.user_ids_by_role(c, Role.UPLOADER.value)
        if not ok:
            raise DomainError("operation_interrupted")
        log.info("content_resubmitted", extra={"ctx": {"content": content_id, "student": student_id}})
        await self.cleanup.process_due()
        await self.notifier.new_submission(content, uploaders, resubmitted=True)
        return content

    # ───────────── review ─────────────
    async def approve(self, reviewer_id: int, content_id: int) -> Content:
        async with self.db.tx() as c:
            await require_role(c, reviewer_id, *REVIEWERS)
            if not await repo.transition(c, content_id, Status.PENDING.value, Status.APPROVING.value,
                                         reviewer_id=reviewer_id):
                status = await repo.get_status(c, content_id)
                raise DomainError("content_not_found" if status is None else "not_pending", status=status)
            content = await repo.get_content(c, content_id)
        protect = protect_for_stage("approved")
        caption = texts.channel_caption(content, approved=True)
        copies: dict[str, Sent] = {}
        try:
            for f in content.files:
                target = self.channels.approved_for(f.kind)
                sent = await self.gw.send_document(target, f.file_id, caption, protect)
                await self.cleanup.hold(content_id, target, sent.message_id, "approve_failed")
                copies[f.kind] = sent
        except Exception as exc:
            log.warning("approve_copy_failed", extra={"ctx": {"content": content_id, "error": str(exc)}})
            await self._rollback(content_id, Status.APPROVING.value, Status.PENDING.value, "approve_failed")
            raise DomainError("approve_failed") from exc

        async with self.db.tx() as c:
            ok = await repo.transition(c, content_id, Status.APPROVING.value, Status.APPROVED.value,
                                       decided_at=utcnow(), rejection_reason=None, reviewer_id=reviewer_id)
            if not ok:
                await repo.activate_holds(c, content_id, "approve_aborted")
            else:
                await repo.release_holds(c, content_id)
                for f in content.files:
                    await repo.enqueue(c, f.chat_id, f.message_id, "approved_temp_removed", content_ref=content_id)
                    await repo.move_file(c, content_id, f.kind, "approved", self.channels.approved_for(f.kind),
                                         copies[f.kind].message_id, protect, copies[f.kind].protected)
                await self._queue_previews(c, content_id, "review_finished")
                content = await repo.get_content(c, content_id)
        if not ok:
            raise DomainError("operation_interrupted")
        log.info("content_approved", extra={"ctx": {"content": content_id, "reviewer": reviewer_id}})
        await self.cleanup.process_due()
        await self.notifier.decision(content)
        return content

    async def reject(self, reviewer_id: int, content_id: int, reason: str) -> Content:
        reason = v.clean_text(reason, min_len=3, max_len=500, code="invalid_reject_reason")
        async with self.db.tx() as c:
            await require_role(c, reviewer_id, *REVIEWERS)
            if not await repo.transition(c, content_id, Status.PENDING.value, Status.REJECTED.value,
                                         rejection_reason=reason, reviewer_id=reviewer_id, decided_at=utcnow()):
                status = await repo.get_status(c, content_id)
                raise DomainError("content_not_found" if status is None else "not_pending", status=status)
            await self._queue_previews(c, content_id, "review_finished")
            content = await repo.get_content(c, content_id)
        log.info("content_rejected", extra={"ctx": {"content": content_id, "reviewer": reviewer_id}})
        await self.cleanup.process_due()
        await self.notifier.decision(content)
        return content

    @staticmethod
    async def _queue_previews(c, content_id: int, reason: str) -> None:
        for chat_id, mid in await repo.previews_for(c, content_id):
            await repo.enqueue(c, chat_id, mid, reason, content_ref=content_id)
        await repo.delete_previews_for(c, content_id)

    async def send_preview(self, viewer_id: int, content_id: int) -> tuple[int, int]:
        """Copy the content files into the reviewer's private chat. Returns (sent, failed)."""
        async with self.db.read() as c:
            viewer = await require_role(c, viewer_id, *REVIEWERS)
            content = await repo.get_content(c, content_id)
        if not content:
            raise DomainError("content_not_found")
        protect = protect_for_role(viewer.role)   # reviewers (admins/uploaders) are never restricted
        caption = texts.channel_caption(content, approved=content.status == Status.APPROVED.value)
        sent = failed = 0
        for f in content.files:
            try:
                mid = (await self.gw.send_document(viewer_id, f.file_id, caption, protect)).message_id
            except Exception as exc:
                failed += 1
                log.warning("preview_failed", extra={"ctx": {"content": content_id, "kind": f.kind, "error": str(exc)}})
                continue
            async with self.db.tx() as c:
                if await repo.get_status(c, content_id) is None:
                    await repo.enqueue(c, viewer_id, mid, "preview_of_deleted")
                else:
                    await repo.add_preview(c, content_id, viewer_id, mid)
            sent += 1
        return sent, failed

    # ───────────── deletion ─────────────
    async def delete(self, admin_id: int, content_id: int) -> DeletionReport:
        async with self.db.tx() as c:
            await require_role(c, admin_id, Role.ADMIN.value)
            content = await repo.get_content(c, content_id)
            if not content:
                raise DomainError("content_not_found")
            if content.status in TRANSITIONAL:
                raise DomainError("content_busy")
            if content.status not in DELETABLE:
                raise DomainError("content_busy")
            job_id = await repo.create_job(c, texts.content_title(content), admin_id)
            for f in content.files:
                await repo.enqueue(c, f.chat_id, f.message_id, f"content_deleted_{f.stage}_{f.kind}",
                                   content_ref=content_id, job_id=job_id)
            for chat_id, mid in await repo.previews_for(c, content_id):
                await repo.enqueue(c, chat_id, mid, "content_deleted_preview", content_ref=content_id, job_id=job_id)
            await repo.attach_open_items_to_job(c, content_id, job_id)
            await repo.delete_content_row(c, content_id)
        log.info("content_deleted", extra={"ctx": {"content": content_id, "admin": admin_id, "job": job_id}})
        return await self.cleanup.process_job(job_id)
