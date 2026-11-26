"""Admin: channel checks and support username.

There is intentionally no protection setting here: student protection is a permanent rule (bot/policy.py).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Ad
from bot.handlers.utils import render, show_error
from bot.keyboards import HOME, cancel_kb, kb
from bot.models import AppUser, Role
from bot.permissions import HasRole
from bot.services.container import Services
from bot.services.errors import DomainError

router = Router(name="admin_settings")
router.message.filter(HasRole(Role.ADMIN.value))
router.callback_query.filter(HasRole(Role.ADMIN.value))


class SettingsForm(StatesGroup):
    support = State()


@router.callback_query(Ad.filter(F.a == "sm"))
async def settings_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await render(cb, texts.AD_SETTINGS_MENU, kb((texts.BTN_CHECK_CHANNELS, Ad(a="ch")),
                                                (texts.BTN_SUPPORT_SETTINGS, Ad(a="su")), HOME))


@router.callback_query(Ad.filter(F.a == "ch"))
async def check_channels(cb: CallbackQuery, svc: Services) -> None:
    rows = []
    for key, cid in svc.config.channels.all().items():
        info = await svc.gateway.channel_status(cid)
        label = texts.AD_CHANNEL_NAMES[key]
        if info["error"]:
            rows.append(texts.AD_CHANNEL_ERROR.format(label=label, cid=cid, error=texts.e(info["error"][:120])))
        else:
            rows.append(texts.AD_CHANNEL_ROW.format(label=label, cid=cid, title=texts.e(info["title"]),
                                                    post=texts.yes_no(info["can_post"]),
                                                    delete=texts.yes_no(info["can_delete"]),
                                                    protected=texts.yes_no(bool(info["protected"])))
                        + texts.AD_CHANNEL_POLICY[key.split("_")[0]])
    stats = await svc.protection.stats()          # read-only information, nothing can be changed here
    note = texts.AD_PROTECTION_NOTE
    if stats["outdated"]:
        note += texts.AD_PROTECTION_PENDING.format(n=stats["outdated"])
    if stats["not_honoured"]:
        note += texts.AD_PROTECTION_NOT_HONOURED.format(n=stats["not_honoured"])
    await render(cb, texts.AD_CHANNELS.format(rows="\n".join(rows), note=note),
                 kb((texts.BTN_REFRESH, Ad(a="ch")), (texts.BTN_BACK, Ad(a="sm")), HOME))


@router.callback_query(Ad.filter(F.a == "su"))
async def support_settings(cb: CallbackQuery, state: FSMContext, svc: Services) -> None:
    await state.clear()
    current = await svc.settings.support_username()
    await render(cb, texts.AD_SUPPORT_SETTINGS.format(current=f"@{texts.e(current)}" if current else "غير محدد"),
                 kb((texts.BTN_EDIT_SUPPORT, Ad(a="sue")), (texts.BTN_BACK, Ad(a="sm")), HOME))


@router.callback_query(Ad.filter(F.a == "sue"))
async def support_edit(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsForm.support)
    await render(cb, texts.AD_ASK_SUPPORT, cancel_kb())


@router.message(SettingsForm.support, F.text)
async def support_save(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    try:
        username = await svc.settings.set_support_username(user.telegram_id, message.text)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.clear()
    await message.answer(texts.AD_SUPPORT_SAVED.format(username=texts.e(username)),
                         reply_markup=kb((texts.BTN_BACK, Ad(a="su")), HOME))
