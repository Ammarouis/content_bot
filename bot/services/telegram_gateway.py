"""Thin wrapper over the Bot API: retries on flood control / network errors and classifies failures."""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError, TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, TelegramServerError,
)
from aiogram.types import InlineKeyboardMarkup

from bot.models import Sent

log = logging.getLogger(__name__)
T = TypeVar("T")

_GONE_MARKERS = ("message to delete not found", "message_id_invalid", "message not found")


class DeleteResult(str, Enum):
    DELETED = "deleted"
    GONE = "gone"          # already removed (counts as success)
    FAILED = "failed"      # retryable


class TelegramGateway:
    def __init__(self, bot: Bot, attempts: int = 4, max_retry_after: float = 60.0) -> None:
        self.bot = bot
        self.attempts = attempts
        self.max_retry_after = max_retry_after

    async def _call(self, op: str, fn: Callable[[], Awaitable[T]]) -> T:
        delay = 1.0
        for attempt in range(1, self.attempts + 1):
            try:
                return await fn()
            except TelegramRetryAfter as exc:
                if attempt == self.attempts or exc.retry_after > self.max_retry_after:
                    raise
                log.warning("telegram_flood_wait", extra={"ctx": {"op": op, "retry_after": exc.retry_after}})
                await asyncio.sleep(exc.retry_after + 0.5)
            except (TelegramNetworkError, TelegramServerError) as exc:
                if attempt == self.attempts:
                    raise
                log.warning("telegram_transient_error", extra={"ctx": {"op": op, "error": str(exc), "attempt": attempt}})
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError("unreachable")

    async def send_document(self, chat_id: int, file_id: str, caption: str | None, protect: bool,
                            silent: bool = False) -> Sent:
        """Post a document by file_id. Returns the message id and the protection flag *reported by Telegram*,
        so protection is verified instead of assumed."""
        msg = await self._call("send_document", lambda: self.bot.send_document(
            chat_id=chat_id, document=file_id, caption=caption, protect_content=protect,
            disable_notification=silent))
        actual = bool(getattr(msg, "has_protected_content", False))
        if protect and not actual:
            log.warning("protection_not_confirmed", extra={"ctx": {"chat_id": chat_id, "message_id": msg.message_id}})
        return Sent(msg.message_id, actual)

    async def delete(self, chat_id: int, message_id: int) -> tuple[DeleteResult, str | None]:
        try:
            await self._call("delete_message", lambda: self.bot.delete_message(chat_id=chat_id, message_id=message_id))
            return DeleteResult.DELETED, None
        except TelegramBadRequest as exc:
            text = str(exc).lower()
            if any(m in text for m in _GONE_MARKERS):
                return DeleteResult.GONE, str(exc)
            return DeleteResult.FAILED, str(exc)
        except TelegramAPIError as exc:
            return DeleteResult.FAILED, str(exc)
        except Exception as exc:  # network etc. after retries
            return DeleteResult.FAILED, f"{type(exc).__name__}: {exc}"

    async def notify(self, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> bool:
        """Best-effort notification; never raises."""
        try:
            await self._call("send_message", lambda: self.bot.send_message(chat_id, text, reply_markup=markup))
            return True
        except Exception as exc:
            log.warning("notify_failed", extra={"ctx": {"chat_id": chat_id, "error": str(exc)}})
            return False

    async def channel_status(self, chat_id: int) -> dict:
        """Report whether the bot can post/delete in a channel and whether saving is restricted there."""
        info: dict[str, Any] = {"ok": False, "title": None, "protected": None, "can_post": False, "can_delete": False,
                                "error": None}
        try:
            chat = await self._call("get_chat", lambda: self.bot.get_chat(chat_id))
            info["title"] = chat.title
            info["protected"] = bool(getattr(chat, "has_protected_content", False))
            me = await self.bot.me()
            member = await self._call("get_chat_member", lambda: self.bot.get_chat_member(chat_id, me.id))
            info["can_post"] = bool(getattr(member, "can_post_messages", False)) or member.status == "creator"
            info["can_delete"] = bool(getattr(member, "can_delete_messages", False)) or member.status == "creator"
            info["ok"] = info["can_post"] and info["can_delete"]
        except Exception as exc:
            info["error"] = str(exc)
        return info
