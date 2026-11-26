"""Review area (Uploader and Admin): pending queue, file preview, approve, reject, and the approved-content
hierarchy (year → specialization → semester → subject → type → items), shared by both roles."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import texts
from bot.callbacks import Ad, Rv
from bot.handlers.utils import PER_PAGE, render, safe_answer, show_error
from bot.keyboards import HOME, cancel_kb, kb, paged
from bot.models import SEMESTERS, TRANSITIONAL, AppUser, Content
from bot.permissions import REVIEWERS, HasRole
from bot.services.container import Services
from bot.services.errors import DomainError

router = Router(name="review")
router.message.filter(HasRole(*REVIEWERS))
router.callback_query.filter(HasRole(*REVIEWERS))

TYPE_BY_IDX = {1: "lecture", 2: "session"}
IDX_BY_TYPE = {v: k for k, v in TYPE_BY_IDX.items()}


class RejectFlow(StatesGroup):
    reason = State()


# ───────────── item card (single implementation for every entry point) ─────────────
def _card(c: Content, user: AppUser) -> tuple[str, InlineKeyboardMarkup]:
    rows: list = []
    if c.files:
        rows.append((texts.BTN_VIEW_FILES, Rv(a="files", x=c.id)))
    if c.status == "pending":
        rows.append([(texts.BTN_APPROVE, Rv(a="ap", x=c.id)), (texts.BTN_REJECT, Rv(a="rj", x=c.id))])
    if user.is_admin and c.status not in TRANSITIONAL:
        rows.append((texts.BTN_DELETE_CONTENT, Ad(a="cd", x=c.id)))
    if c.status == "approved":
        back = Rv(a="atl", x=c.subject_id, y=IDX_BY_TYPE[c.content_type])
    elif c.status == "pending" or not user.is_admin:
        back = Rv(a="pl")
    else:
        back = Ad(a="cm")
    rows.append((texts.BTN_BACK, back))
    return texts.content_details(c), kb(*rows, HOME)


# ───────────── pending ─────────────
@router.callback_query(Rv.filter(F.a == "pl"))
async def pending_list(cb: CallbackQuery, callback_data: Rv, state: FSMContext, svc: Services) -> None:
    await state.clear()
    items, total = await svc.content.pending(callback_data.p, PER_PAGE)
    if not total:
        return await render(cb, texts.RV_PENDING_EMPTY, kb(HOME))
    await render(cb, texts.RV_PENDING_TITLE.format(total=total),
                 paged(items, lambda c: (texts.content_button(c), Rv(a="pv", x=c.id)), callback_data.p, total,
                       PER_PAGE, lambda p: Rv(a="pl", p=p), [HOME]))


@router.callback_query(Rv.filter(F.a.in_({"pv", "av"})))
async def view_item(cb: CallbackQuery, callback_data: Rv, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    try:
        c = await svc.content.get(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, *_card(c, user))


@router.callback_query(Rv.filter(F.a == "files"))
async def view_files(cb: CallbackQuery, callback_data: Rv, user: AppUser, svc: Services) -> None:
    try:
        sent, failed = await svc.content.send_preview(user.telegram_id, callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    if sent == 0 and failed == 0:
        return await safe_answer(cb, texts.RV_NO_FILES, alert=True)
    note = texts.RV_FILES_SENT.format(sent=sent) if not failed else texts.RV_FILES_PARTIAL.format(sent=sent,
                                                                                                    failed=failed)
    await safe_answer(cb, note, alert=bool(failed))
    try:  # re-send the card below the files so the action buttons stay at hand
        c = await svc.content.get(callback_data.x)
    except DomainError:
        return
    text, markup = _card(c, user)
    await cb.bot.send_message(user.telegram_id, text, reply_markup=markup)


# ───────────── approve ─────────────
@router.callback_query(Rv.filter(F.a == "ap"))
async def approve_confirm(cb: CallbackQuery, callback_data: Rv, svc: Services) -> None:
    try:
        c = await svc.content.get(callback_data.x)
        if c.status != "pending":
            raise DomainError("not_pending", status=c.status)
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.RV_CONFIRM_APPROVE.format(title=texts.e(texts.content_title(c))),
                 kb((texts.BTN_CONFIRM_APPROVE, Rv(a="apy", x=c.id)), (texts.BTN_BACK, Rv(a="pv", x=c.id))))


@router.callback_query(Rv.filter(F.a == "apy"))
async def approve_do(cb: CallbackQuery, callback_data: Rv, user: AppUser, svc: Services) -> None:
    await render(cb, texts.RV_APPROVING)
    try:
        c = await svc.content.approve(user.telegram_id, callback_data.x)
    except DomainError as exc:
        return await render(cb, texts.error(exc.code, **exc.params), kb((texts.BTN_PENDING, Rv(a="pl")), HOME))
    await render(cb, texts.RV_APPROVED_DONE.format(title=texts.e(texts.content_title(c))),
                 kb((texts.BTN_PENDING, Rv(a="pl")), HOME))


# ───────────── reject ─────────────
@router.callback_query(Rv.filter(F.a == "rj"))
async def reject_start(cb: CallbackQuery, callback_data: Rv, state: FSMContext, svc: Services) -> None:
    try:
        c = await svc.content.get(callback_data.x)
        if c.status != "pending":
            raise DomainError("not_pending", status=c.status)
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.set_state(RejectFlow.reason)
    await state.update_data(content_id=c.id)
    await render(cb, texts.RV_ASK_REJECT.format(title=texts.e(texts.content_title(c))), cancel_kb())


@router.message(RejectFlow.reason, F.text)
async def reject_reason(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    try:
        c = await svc.content.reject(user.telegram_id, data["content_id"], message.text)
    except DomainError as exc:
        if exc.code == "invalid_reject_reason":
            return await show_error(message, exc, cancel_kb())
        await state.clear()
        return await show_error(message, exc, kb((texts.BTN_PENDING, Rv(a="pl")), HOME))
    await state.clear()
    await message.answer(texts.RV_REJECTED_DONE.format(title=texts.e(texts.content_title(c)),
                                                       reason=texts.e(c.rejection_reason)),
                         reply_markup=kb((texts.BTN_PENDING, Rv(a="pl")), HOME))


@router.message(RejectFlow.reason)
async def reject_expect_text(message: Message) -> None:
    await message.answer(texts.ST_EXPECT_TEXT, reply_markup=cancel_kb())


# ───────────── approved hierarchy ─────────────
def _with(label: str, n: int) -> str:
    return f"{label} ({n})"


@router.callback_query(Rv.filter(F.a == "ay"))
async def approved_years(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    counts = await svc.content.approved_counts()
    rows = [(_with(y.name, counts.year(y.id)), Rv(a="ayy", x=y.id)) for y in await svc.academic.years()]
    back = (texts.BTN_BACK, Ad(a="cm")) if user.is_admin else HOME
    await render(cb, texts.AP_YEARS, kb(*rows, back))


@router.callback_query(Rv.filter(F.a == "ayy"))
async def approved_year(cb: CallbackQuery, callback_data: Rv, svc: Services) -> None:
    try:
        year = await svc.academic.year(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    if not year.requires_specialization:
        return await _semesters(cb, svc, year.id, None)
    specs = await svc.academic.specializations(year.id)
    back = (texts.BTN_BACK, Rv(a="ay"))
    if not specs:
        return await render(cb, texts.AP_NO_SPECS, kb(back, HOME))
    counts = await svc.content.approved_counts()
    rows = [(_with(s.name, counts.spec(s.id)), Rv(a="asp", x=s.id)) for s in specs]
    await render(cb, texts.AP_SPECS.format(path=texts.path(year.name)), kb(*rows, back, HOME))


@router.callback_query(Rv.filter(F.a == "asp"))
async def approved_spec(cb: CallbackQuery, callback_data: Rv, svc: Services) -> None:
    try:
        spec = await svc.academic.specialization(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await _semesters(cb, svc, spec.year_id, spec.id)


async def _path(svc: Services, year_id: int, spec_id: int | None, semester: int | None = None) -> list[str]:
    parts = [(await svc.academic.year(year_id)).name]
    if spec_id:
        parts.append((await svc.academic.specialization(spec_id)).name)
    if semester:
        parts.append(texts.SEMESTER_NAMES[semester])
    return parts


async def _semesters(cb: CallbackQuery, svc: Services, year_id: int, spec_id: int | None) -> None:
    counts = await svc.content.approved_counts()
    rows = [(_with(texts.SEMESTER_NAMES[sem], counts.semester(year_id, spec_id, sem)),
             Rv(a="asm", x=year_id, y=spec_id or 0, p=sem)) for sem in SEMESTERS]
    back = Rv(a="ayy", x=year_id) if spec_id else Rv(a="ay")
    await render(cb, texts.AP_SEMESTERS.format(path=texts.path(*await _path(svc, year_id, spec_id))),
                 kb(*rows, (texts.BTN_BACK, back), HOME))


@router.callback_query(Rv.filter(F.a == "asm"))
async def approved_subjects(cb: CallbackQuery, callback_data: Rv, svc: Services) -> None:
    year_id, spec_id, semester = callback_data.x, callback_data.y or None, callback_data.p
    try:
        path = await _path(svc, year_id, spec_id, semester)
    except DomainError as exc:
        return await show_error(cb, exc)
    back = (texts.BTN_BACK, Rv(a="asp", x=spec_id) if spec_id else Rv(a="ayy", x=year_id))
    subjects = await svc.academic.subjects(year_id, spec_id, semester) if semester in SEMESTERS else []
    if not subjects:
        return await render(cb, texts.AP_NO_SUBJECTS, kb(back, HOME))
    counts = await svc.content.approved_counts()
    rows = [(_with(f"{s.name} ({s.code})", counts.subject(s.id)), Rv(a="asb", x=s.id)) for s in subjects]
    await render(cb, texts.AP_SUBJECTS.format(path=texts.path(*path)), kb(*rows, back, HOME))


@router.callback_query(Rv.filter(F.a == "asb"))
async def approved_types(cb: CallbackQuery, callback_data: Rv, svc: Services) -> None:
    try:
        s = await svc.academic.subject(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    counts = await svc.content.approved_counts()
    path = await _path(svc, s.year_id, s.specialization_id, s.semester) + [f"{s.name} ({s.code})"]
    rows = [[(_with(texts.TYPE_PLURAL[t], counts.type(s.id, t)), Rv(a="atl", x=s.id, y=i))
             for i, t in TYPE_BY_IDX.items()]]
    back = Rv(a="asm", x=s.year_id, y=s.specialization_id or 0, p=s.semester)
    await render(cb, texts.AP_TYPES.format(path=texts.path(*path)), kb(*rows, (texts.BTN_BACK, back), HOME))


@router.callback_query(Rv.filter(F.a == "atl"))
async def approved_list(cb: CallbackQuery, callback_data: Rv, state: FSMContext, svc: Services) -> None:
    await state.clear()
    ctype = TYPE_BY_IDX.get(callback_data.y)
    try:
        s = await svc.academic.subject(callback_data.x)
        if not ctype:
            raise DomainError("invalid_type")
    except DomainError as exc:
        return await show_error(cb, exc)
    items, total = await svc.content.approved_list(s.id, ctype, callback_data.p, PER_PAGE)
    back = (texts.BTN_BACK, Rv(a="asb", x=s.id))
    path = await _path(svc, s.year_id, s.specialization_id, s.semester) + [f"{s.name} ({s.code})"]
    if not total:
        return await render(cb, texts.RV_APPROVED_EMPTY, kb(back, HOME))
    await render(cb, texts.AP_LIST.format(path=texts.path(*path), ctype=texts.TYPE_PLURAL[ctype], total=total),
                 paged(items, lambda c: (f"{texts.TYPE_NAMES[c.content_type]} {c.number}", Rv(a="av", x=c.id)),
                       callback_data.p, total, PER_PAGE, lambda p: Rv(a="atl", x=s.id, y=callback_data.y, p=p),
                       [back, HOME]))
