"""Permanent student content protection — a hardcoded system rule.

This is deliberately *not* a setting: nothing in the database, the admin dashboard or the UI can change it.

Rule
----
* Everything the bot delivers to a **student** (messages, PDF/TEX documents, copies, forwards, media, …) is sent with
  Telegram's ``protect_content`` flag.
* The **approved channels** hold the published, student-facing material, so every post there is protected as well.
* **Admins and uploaders** (and the temporary review channels they work in) always receive unrestricted messages.

Enforcement happens in two layers:

1. Services pass the flag explicitly (:func:`protect_for_role` / :func:`protect_for_stage`), so it is stored with
   every file and existing posts can be checked and re-published (see ``services/protection.py``).
2. :class:`StudentProtectionMiddleware` runs on *every* outgoing Bot API request and overwrites ``protect_content``
   according to the recipient. Any present or future delivery path — including code that forgets the flag — is
   therefore covered. If the recipient's role cannot be determined, it fails closed (protects).

Telegram limitations (cannot be solved by any bot): ``protect_content`` blocks forwarding and saving; the official
mobile apps also block screenshots/screen recording of protected messages, but desktop/web clients do not reliably do
so, and nothing prevents photographing the screen.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType

from bot.models import Role

if TYPE_CHECKING:
    from aiogram import Bot

    from bot.config import Channels
    from bot.db.database import Database

log = logging.getLogger(__name__)

PROTECTED_ROLE = Role.STUDENT.value     # the only protected audience — permanent


def protect_for_role(role: str | None) -> bool:
    """Private deliveries: protected exactly when the recipient is a student."""
    return role == PROTECTED_ROLE


def protect_for_stage(stage: str) -> bool:
    """Channel posts: approved channels are student-facing (protected); temporary channels are for uploaders."""
    return stage == "approved"


def supports_protection(method: TelegramMethod) -> bool:
    return "protect_content" in type(method).model_fields


class StudentProtectionMiddleware(BaseRequestMiddleware):
    """Sets ``protect_content`` on every outgoing request that supports it, based on who receives it."""

    def __init__(self, db: Database, channels: Channels, admin_ids: frozenset[int]) -> None:
        self.db = db
        self.approved = {channels.approved_pdf, channels.approved_tex}
        self.temp = {channels.temp_pdf, channels.temp_tex}
        self.admin_ids = admin_ids

    async def required(self, chat_id: Any) -> bool | None:
        """True/False = the flag this recipient must get; None = not a chat this bot manages (left unchanged)."""
        if not isinstance(chat_id, int):
            return None
        if chat_id in self.approved:
            return True
        if chat_id in self.temp:
            return False
        if chat_id < 0:
            return None
        if chat_id in self.admin_ids:
            return False
        try:
            role = await self.db.role_of(chat_id)
        except Exception:                      # never deliver unprotected to a possible student
            log.exception("protection_role_lookup_failed", extra={"ctx": {"chat_id": chat_id}})
            return True
        return protect_for_role(role)

    async def __call__(self, make_request: NextRequestMiddlewareType[TelegramType], bot: Bot,
                       method: TelegramMethod[TelegramType]) -> Any:
        if supports_protection(method):
            required = await self.required(getattr(method, "chat_id", None))
            if required is not None:
                if required and method.protect_content is not True:
                    log.debug("protection_enforced", extra={"ctx": {"method": type(method).__name__}})
                method.protect_content = required
        return await make_request(bot, method)
