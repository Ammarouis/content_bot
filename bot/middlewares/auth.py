"""Authentication middleware: private chats only, registered users only. Injects ``user`` for handlers/filters."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import texts
from bot.services.users import UserService

log = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    def __init__(self, users: UserService) -> None:
        self.users = users

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        if isinstance(event, Message):
            chat, tg_user = event.chat, event.from_user
        elif isinstance(event, CallbackQuery):
            chat = event.message.chat if event.message else None
            tg_user = event.from_user
        else:
            return None
        if tg_user is None or tg_user.is_bot or (chat is not None and chat.type != "private"):
            return None  # ignore groups, channels and bots entirely

        user = await self.users.get(tg_user.id)
        if user is None:
            log.info("unauthorized_access", extra={"ctx": {"telegram_id": tg_user.id}})
            if isinstance(event, Message):
                await event.answer(texts.UNAUTHORIZED.format(tid=tg_user.id))
            else:
                await event.answer(texts.UNAUTHORIZED_ALERT, show_alert=True)
            return None
        data["user"] = user
        return await handler(event, data)
