"""Inline keyboard helpers shared by all handlers."""
from __future__ import annotations

from typing import Callable, Iterable, Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.callbacks import Nav

Button = tuple[str, CallbackData | str]


def btn(text: str, data: CallbackData | str) -> InlineKeyboardButton:
    if isinstance(data, str) and data.startswith(("https://", "tg://")):
        return InlineKeyboardButton(text=text, url=data)
    return InlineKeyboardButton(text=text, callback_data=data.pack() if isinstance(data, CallbackData) else data)


def kb(*rows: Sequence[Button] | Button | None) -> InlineKeyboardMarkup:
    """kb(("A", cb), [("B", cb), ("C", cb)], None) -> one button per tuple row, lists form multi-button rows."""
    keyboard = []
    for row in rows:
        if row is None:
            continue
        if isinstance(row, tuple):
            row = [row]
        if row:
            keyboard.append([btn(t, d) for t, d in row])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


HOME: Button = (texts.BTN_HOME, Nav(to="home"))
CANCEL: Button = (texts.BTN_CANCEL, Nav(to="cancel"))


def cancel_kb() -> InlineKeyboardMarkup:
    return kb(CANCEL)


def paged(items: Iterable, make: Callable[[object], Button], page: int, total: int, per: int,
          page_cb: Callable[[int], CallbackData], footer: Sequence[Sequence[Button] | Button] = ()
          ) -> InlineKeyboardMarkup:
    rows: list = [make(i) for i in items]
    pages = max(1, (total + per - 1) // per)
    nav: list[Button] = []
    if page > 0:
        nav.append((texts.BTN_PREV, page_cb(page - 1)))
    if pages > 1:
        nav.append((f"{page + 1}/{pages}", page_cb(page)))
    if page < pages - 1:
        nav.append((texts.BTN_NEXT, page_cb(page + 1)))
    if nav:
        rows.append(nav)
    rows.extend(footer)
    return kb(*rows)


def support_kb(username: str | None) -> InlineKeyboardMarkup:
    if username:
        return kb((texts.BTN_CONTACT_SUPPORT, f"https://t.me/{username}"), HOME)
    return kb(HOME)
