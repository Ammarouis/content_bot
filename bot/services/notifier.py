"""Notification port used by services; the Telegram/Arabic implementation lives in bot/notifications.py."""
from __future__ import annotations

from typing import Protocol

from bot.models import Content


class Notifier(Protocol):
    async def new_submission(self, content: Content, uploader_ids: list[int], resubmitted: bool) -> None: ...

    async def decision(self, content: Content) -> None: ...

    async def operation_rolled_back(self, student_id: int, content_id: int, status: str) -> None: ...

    async def job_finished(self, requested_by: int, job_id: int, description: str, counts: dict,
                           status: str) -> None: ...


class NullNotifier:
    async def new_submission(self, *a, **k) -> None: ...

    async def decision(self, *a, **k) -> None: ...

    async def operation_rolled_back(self, *a, **k) -> None: ...

    async def job_finished(self, *a, **k) -> None: ...
