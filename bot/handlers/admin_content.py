"""Admin: approved content browser, search, confirmed deletion and the cleanup queue."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Ad, Rv
from bot.handlers.utils import PER_PAGE, render, safe_answer, show_error
from bot.keyboards import HOME, cancel_kb, kb, paged
from bot.models import TRANSITIONAL, AppUser, Role
from bot.permissions import HasRole
from bot.services import validators as v
from bot.services.container import Services
from bot.services.errors import DomainError

router = Router(name="admin_content")
router.message.filter(HasRole(Role.ADMIN.value))
router.callback_query.filter(HasRole(Role.ADMIN.value))

TYPE_BY_IDX = {0: None, 1: "lecture", 2: "session"}


class SearchForm(StatesGroup):
    code = State()
    number = State()


@router.callback_query(Ad.filter(F.a == "cm"))
async def content_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await render(cb, texts.AD_CONTENT_MENU, kb((texts.BTN_APPROVED_CONTENT, Rv(a="ay")), (texts.BTN_SEARCH, Ad(a="cs")),
                                               (texts.BTN_CLEANUP, Ad(a="cq")), HOME))


# ───────────── deletion (item cards live in the shared review router) ─────────────
@router.callback_query(Ad.filter(F.a == "cd"))
async def delete_confirm(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    try:
        c = await svc.content.get(callback_data.x)
        if c.status in TRANSITIONAL:
            raise DomainError("content_busy")
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.AD_CONFIRM_DELETE.format(details=texts.content_details(c)),
                 kb((texts.BTN_CONFIRM_DELETE, Ad(a="cdy", x=c.id)), (texts.BTN_CANCEL, Rv(a="av", x=c.id))))


@router.callback_query(Ad.filter(F.a == "cdy"))
async def delete_do(cb: CallbackQuery, callback_data: Ad, user: AppUser, svc: Services) -> None:
    try:
        c = await svc.content.get(callback_data.x)   # remembered for the back button
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.AD_DELETING)
    back = (texts.BTN_BACK, Rv(a="atl", x=c.subject_id, y=1 if c.content_type == "lecture" else 2)
            if c.status == "approved" else Ad(a="cm"))
    try:
        report = await svc.content.delete(user.telegram_id, c.id)
    except DomainError as exc:
        return await render(cb, texts.error(exc.code, **exc.params), kb(back, HOME))
    title = texts.e(report.description)
    if report.complete:
        text = texts.AD_DELETE_DONE.format(title=title, done=report.done)
    else:
        text = texts.AD_DELETE_PARTIAL.format(title=title, done=report.done, pending=report.pending,
                                              failed=report.failed)
    await render(cb, text, kb(back, (texts.BTN_CLEANUP, Ad(a="cq")), HOME))


# ───────────── search ─────────────
@router.callback_query(Ad.filter(F.a == "cs"))
async def search_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SearchForm.code)
    await render(cb, texts.AD_ASK_SEARCH_CODE, cancel_kb())


@router.message(SearchForm.code, F.text)
async def search_code(message: Message, state: FSMContext, svc: Services) -> None:
    try:
        s = await svc.academic.subject_by_code(message.text)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.set_state(None)
    await state.update_data(subject_id=s.id)
    label = f"{s.name} ({s.code})"
    await message.answer(texts.AD_SEARCH_TYPE.format(subject=texts.e(label)),
                         reply_markup=kb([(texts.TYPE_NAMES["lecture"], Ad(a="cst", x=s.id, y=1)),
                                          (texts.TYPE_NAMES["session"], Ad(a="cst", x=s.id, y=2))],
                                         (texts.BTN_ALL, Ad(a="csr", x=s.id, y=0)), (texts.BTN_CANCEL, Ad(a="cm"))))


@router.callback_query(Ad.filter(F.a == "cst"))
async def search_type(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    ctype = TYPE_BY_IDX.get(callback_data.y)
    try:
        s = await svc.academic.subject(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    if not ctype:
        return await safe_answer(cb, texts.error("invalid_type"), alert=True)
    await state.set_state(SearchForm.number)
    await state.update_data(subject_id=s.id, type_idx=callback_data.y)
    await render(cb, texts.AD_SEARCH_NUMBER.format(subject=texts.e(f"{s.name} ({s.code})"),
                                                   ctype=texts.TYPE_NAMES[ctype]),
                 kb((texts.BTN_SHOW_ALL, Ad(a="csr", x=s.id, y=callback_data.y)), (texts.BTN_CANCEL, Ad(a="cm"))))


async def _results(event, svc: Services, subject_id: int, type_idx: int, number: int | None, page: int) -> None:
    s = await svc.academic.subject(subject_id)
    items, total = await svc.content.search(subject_id, TYPE_BY_IDX.get(type_idx), number, page, PER_PAGE)
    footer = [(texts.BTN_SEARCH, Ad(a="cs")), (texts.BTN_BACK, Ad(a="cm"))]
    if not total:
        return await render(event, texts.AD_SEARCH_EMPTY, kb(*footer))
    await render(event, texts.AD_SEARCH_RESULTS.format(subject=texts.e(f"{s.name} ({s.code})"), total=total),
                 paged(items, lambda c: (texts.content_button(c, with_status=True), Rv(a="av", x=c.id)), page, total,
                       PER_PAGE, lambda p: Ad(a="csr", x=subject_id, y=type_idx, p=p), footer))


@router.message(SearchForm.number, F.text)
async def search_number(message: Message, state: FSMContext, svc: Services) -> None:
    data = await state.get_data()
    try:
        number = v.content_number(message.text)
        await state.clear()
        await _results(message, svc, data["subject_id"], data["type_idx"], number, 0)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())


@router.callback_query(Ad.filter(F.a == "csr"))
async def search_results(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    try:
        await _results(cb, svc, callback_data.x, callback_data.y, None, callback_data.p)
    except DomainError as exc:
        await show_error(cb, exc)


# ───────────── cleanup queue ─────────────
async def _cleanup_screen(cb: CallbackQuery, svc: Services, prefix: str = "") -> None:
    stats = await svc.cleanup.stats()
    failed_list = ""
    failed = await svc.cleanup.failed_items(5)
    if failed:
        failed_list = texts.AD_FAILED_HEADER + "".join(
            texts.AD_FAILED_ITEM.format(chat=r["chat_id"], mid=r["message_id"], error=texts.e((r["last_error"] or "")[:80]))
            for r in failed)
    text = texts.AD_CLEANUP_STATUS.format(
        pending=stats["pending"], failed=stats["failed"], held=stats["held"], done=stats["done"],
        jobs_in_progress=stats.get("jobs_in_progress", 0), jobs_needs_attention=stats.get("jobs_needs_attention", 0),
        failed_list=failed_list)
    rows = [(texts.BTN_RUN_CLEANUP, Ad(a="cqn"))]
    if stats["failed"]:
        rows.insert(0, (texts.BTN_RETRY_FAILED, Ad(a="cqr")))
    await render(cb, (prefix + "\n\n" if prefix else "") + text,
                 kb(*rows, (texts.BTN_REFRESH, Ad(a="cq")), (texts.BTN_BACK, Ad(a="cm")), HOME))


@router.callback_query(Ad.filter(F.a == "cq"))
async def cleanup_status(cb: CallbackQuery, state: FSMContext, svc: Services) -> None:
    await state.clear()
    await _cleanup_screen(cb, svc)


@router.callback_query(Ad.filter(F.a == "cqr"))
async def cleanup_retry(cb: CallbackQuery, user: AppUser, svc: Services) -> None:
    try:
        n = await svc.cleanup.retry_failed(user.telegram_id)
    except DomainError as exc:
        return await show_error(cb, exc)
    await _cleanup_screen(cb, svc, texts.AD_RETRIED.format(n=n))


@router.callback_query(Ad.filter(F.a == "cqn"))
async def cleanup_now(cb: CallbackQuery, svc: Services) -> None:
    n = await svc.cleanup.process_due()
    await svc.cleanup.finalize_jobs()
    await _cleanup_screen(cb, svc, texts.AD_CLEANUP_RAN.format(n=n))
