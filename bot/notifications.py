"""Arabic Telegram notifications (implements services.notifier.Notifier)."""
from __future__ import annotations

from bot import texts
from bot.callbacks import Ad, Rv, St
from bot.keyboards import kb
from bot.models import Content
from bot.services.telegram_gateway import TelegramGateway


class TelegramNotifier:
    def __init__(self, gateway: TelegramGateway) -> None:
        self.gw = gateway

    async def new_submission(self, content: Content, uploader_ids: list[int], resubmitted: bool) -> None:
        template = texts.RV_RESUBMISSION if resubmitted else texts.RV_NEW_SUBMISSION
        text = template.format(title=texts.e(texts.content_title(content)), student=texts.e(content.student_name))
        markup = kb((texts.RV_BTN_OPEN, Rv(a="pv", x=content.id)))
        for uid in uploader_ids:
            await self.gw.notify(uid, text, markup)

    async def decision(self, content: Content) -> None:
        if not content.student_id:
            return
        title = texts.e(texts.content_title(content))
        if content.status == "approved":
            await self.gw.notify(content.student_id,
                                 texts.NOTIFY_APPROVED.format(title=title, subject=texts.e(content.subject_name)))
        elif content.status == "rejected":
            await self.gw.notify(
                content.student_id,
                texts.NOTIFY_REJECTED.format(title=title, subject=texts.e(content.subject_name),
                                             reason=texts.e(content.rejection_reason)),
                kb((texts.BTN_OPEN_REJECTED, St(a="rj", x=content.id))))

    async def operation_rolled_back(self, student_id: int, content_id: int, status: str) -> None:
        template = texts.NOTIFY_ROLLED_BACK_UPLOAD if status == "uploading" else texts.NOTIFY_ROLLED_BACK_RESUB
        await self.gw.notify(student_id, template.format(cid=content_id))

    async def job_finished(self, requested_by: int, job_id: int, description: str, counts: dict, status: str) -> None:
        if status == "completed":
            text = texts.AD_JOB_DONE.format(job=job_id, title=texts.e(description), done=counts["done"])
        else:
            text = texts.AD_JOB_ATTENTION.format(job=job_id, title=texts.e(description), done=counts["done"],
                                                 failed=counts["failed"])
        await self.gw.notify(requested_by, text, kb((texts.BTN_CLEANUP, Ad(a="cq"))))
