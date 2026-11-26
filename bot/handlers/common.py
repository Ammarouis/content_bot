"""/start, main menus, support, cancel and the final fallback router."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import texts
from bot.callbacks import Ad, Nav, Rv, St
from bot.handlers.utils import render, safe_answer
from bot.keyboards import cancel_kb, kb, support_kb
from bot.models import AppUser
from bot.services.container import Services

router = Router(name="common")
fallback_router = Router(name="fallback")


async def main_menu(user: AppUser, svc: Services) -> tuple[str, InlineKeyboardMarkup]:
    text = texts.WELCOME[user.role].format(name=texts.e(user.full_name))
    if user.role == "student":
        markup = kb((texts.BTN_MY_SUBJECTS, St(a="subs")), (texts.BTN_RECENT, St(a="recent")),
                    (texts.BTN_UPLOAD, St(a="up")), (texts.BTN_REJECTED, St(a="rej")),
                    (texts.BTN_SUPPORT, Nav(to="support")))
    elif user.role == "uploader":
        _, pending = await svc.content.pending(0, 1)
        markup = kb((f"{texts.BTN_PENDING} ({pending})", Rv(a="pl")), (texts.BTN_APPROVED, Rv(a="ay")),
                    (texts.BTN_SUPPORT, Nav(to="support")))
    else:
        _, pending = await svc.content.pending(0, 1)
        markup = kb((texts.BTN_USERS, Ad(a="um")), (texts.BTN_ACADEMIC, Ad(a="acm")),
                    (texts.BTN_CONTENT, Ad(a="cm")), (f"{texts.BTN_REVIEW} ({pending})", Rv(a="pl")),
                    (texts.BTN_SETTINGS, Ad(a="sm")))
    return text, markup


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    text, markup = await main_menu(user, svc)
    await message.answer(text, reply_markup=markup)


@router.callback_query(Nav.filter(F.to == "home"))
async def nav_home(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    text, markup = await main_menu(user, svc)
    await render(cb, text, markup)


@router.callback_query(Nav.filter(F.to == "cancel"))
async def nav_cancel(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    text, markup = await main_menu(user, svc)
    await render(cb, f"{texts.CANCELLED}\n\n{text}", markup)


@router.callback_query(Nav.filter(F.to == "support"))
async def nav_support(cb: CallbackQuery, state: FSMContext, svc: Services) -> None:
    await state.clear()
    username = await svc.settings.support_username()
    text = texts.SUPPORT_INFO.format(username=texts.e(username)) if username else texts.SUPPORT_NOT_SET
    await render(cb, text, support_kb(username))


# ── fallback: anything not handled by a router the user is permitted to use ──
@fallback_router.callback_query()
async def fallback_callback(cb: CallbackQuery) -> None:
    await safe_answer(cb, texts.STALE_BUTTON, alert=True)


@fallback_router.message()
async def fallback_message(message: Message, state: FSMContext) -> None:
    if await state.get_state():
        await message.answer(texts.ST_EXPECT_TEXT, reply_markup=cancel_kb())
    else:
        await message.answer(texts.USE_BUTTONS)
