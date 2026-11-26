"""Shared rendering / error helpers for handlers."""
from __future__ import annotations

import logging
import re

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import texts
from bot.models import FileInfo
from bot.services.errors import DomainError

log = logging.getLogger(__name__)
PER_PAGE = 8
_TAG_RE = re.compile(r"<[^>]+>")


async def render(event: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit the menu message in place for callbacks; send a new message otherwise."""
    if isinstance(event, CallbackQuery):
        msg = event.message
        edited = False
        if isinstance(msg, Message) and msg.text is not None:
            try:
                await msg.edit_text(text, reply_markup=markup)
                edited = True
            except TelegramBadRequest as exc:
                edited = "message is not modified" in str(exc)
        if not edited:
            await event.bot.send_message(event.from_user.id, text, reply_markup=markup)
        await safe_answer(event)
    else:
        await event.answer(text, reply_markup=markup)


async def safe_answer(cb: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    try:
        await cb.answer(text, show_alert=alert)
    except TelegramBadRequest:
        pass  # query too old / already answered


def plain(text: str) -> str:
    return _TAG_RE.sub("", text)


async def show_error(event: Message | CallbackQuery, exc: DomainError,
                     markup: InlineKeyboardMarkup | None = None) -> None:
    text = texts.error(exc.code, **exc.params)
    if isinstance(event, CallbackQuery):
        await safe_answer(event, plain(text)[:190], alert=True)
    else:
        await event.answer(text, reply_markup=markup)


def file_info(message: Message) -> FileInfo | None:
    doc = message.document
    if not doc:
        return None
    return FileInfo(file_id=doc.file_id, file_unique_id=doc.file_unique_id,
                    file_name=doc.file_name or "file", file_size=doc.file_size or 0)
