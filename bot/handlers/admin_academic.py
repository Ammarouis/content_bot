"""Admin: academic years, specializations and subjects."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Ad
from bot.handlers.utils import render, safe_answer, show_error
from bot.keyboards import HOME, cancel_kb, kb
from bot.models import SEMESTERS, AppUser, Role
from bot.permissions import HasRole
from bot.services import validators as v
from bot.services.container import Services
from bot.services.errors import DomainError

router = Router(name="admin_academic")
router.message.filter(HasRole(Role.ADMIN.value))
router.callback_query.filter(HasRole(Role.ADMIN.value))


class AcademicForm(StatesGroup):
    spec_name = State()
    spec_rename = State()
    subject_name = State()
    subject_code = State()
    subject_new_name = State()
    subject_new_code = State()


@router.callback_query(Ad.filter(F.a == "acm"))
async def academic_menu(cb: CallbackQuery, state: FSMContext, svc: Services) -> None:
    await state.clear()
    unconfirmed = await svc.academic.unconfirmed_subjects()
    extra = (texts.BTN_UNCONFIRMED.format(n=len(unconfirmed)), Ad(a="sbu")) if unconfirmed else None
    await render(cb, texts.AD_ACADEMIC_MENU, kb((texts.BTN_YEARS, Ad(a="yrs")), (texts.BTN_SUBJECTS, Ad(a="sby0")),
                                                extra, HOME))


@router.callback_query(Ad.filter(F.a == "sbu"))
async def unconfirmed_subjects(cb: CallbackQuery, svc: Services) -> None:
    subjects = await svc.academic.unconfirmed_subjects()
    rows = [(f"{s.name} ({s.code}) • {s.year_name}", Ad(a="sb", x=s.id)) for s in subjects]
    await render(cb, texts.AD_UNCONFIRMED_TITLE if subjects else texts.EMPTY_LIST,
                 kb(*rows, (texts.BTN_BACK, Ad(a="acm")), HOME))


# ───────────── years & specializations ─────────────
@router.callback_query(Ad.filter(F.a == "yrs"))
async def years(cb: CallbackQuery, state: FSMContext, svc: Services) -> None:
    await state.clear()
    rows = [(f"{y.name}" + (" • اختصاص إلزامي" if y.requires_specialization else ""), Ad(a="yr", x=y.id))
            for y in await svc.academic.years()]
    await render(cb, texts.AD_YEARS_TITLE, kb(*rows, (texts.BTN_BACK, Ad(a="acm"))))


@router.callback_query(Ad.filter(F.a == "yr"))
async def year_view(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    try:
        year = await svc.academic.year(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    back = (texts.BTN_BACK, Ad(a="yrs"))
    if not year.requires_specialization:
        return await render(cb, texts.AD_YEAR_NO_SPEC.format(year=texts.e(year.name)),
                            kb((texts.BTN_SUBJECTS, Ad(a="sby", x=year.id)), back))
    specs = await svc.academic.specializations(year.id)
    rows = [(s.name, Ad(a="sp", x=s.id)) for s in specs]
    await render(cb, texts.AD_YEAR_SPECS.format(year=texts.e(year.name), n=len(specs)),
                 kb(*rows, (texts.BTN_ADD_SPEC, Ad(a="spa", x=year.id)), back, HOME))


@router.callback_query(Ad.filter(F.a == "spa"))
async def spec_add_start(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    try:
        year = await svc.academic.year(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.set_state(AcademicForm.spec_name)
    await state.update_data(year_id=year.id)
    await render(cb, texts.AD_ASK_SPEC_NAME.format(year=texts.e(year.name)), cancel_kb())


@router.message(AcademicForm.spec_name, F.text)
async def spec_add(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    try:
        await svc.academic.add_specialization(user.telegram_id, data["year_id"], message.text)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.clear()
    await message.answer(texts.AD_SPEC_ADDED, reply_markup=kb((texts.BTN_BACK, Ad(a="yr", x=data["year_id"])), HOME))


@router.callback_query(Ad.filter(F.a == "sp"))
async def spec_view(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    try:
        spec = await svc.academic.specialization(callback_data.x)
        year = await svc.academic.year(spec.year_id)
    except DomainError as exc:
        return await show_error(cb, exc)
    n = len(await svc.academic.subjects(year.id, spec.id))
    await render(cb, texts.AD_SPEC_DETAILS.format(name=texts.e(spec.name), year=texts.e(year.name), n=n),
                 kb((texts.BTN_SUBJECTS, Ad(a="sbs", x=spec.id)),
                    [(texts.BTN_RENAME, Ad(a="spr", x=spec.id)), (texts.BTN_DELETE_SPEC, Ad(a="spd", x=spec.id))],
                    (texts.BTN_BACK, Ad(a="yr", x=year.id)), HOME))


@router.callback_query(Ad.filter(F.a == "spr"))
async def spec_rename_start(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    try:
        spec = await svc.academic.specialization(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.set_state(AcademicForm.spec_rename)
    await state.update_data(spec_id=spec.id)
    await render(cb, texts.AD_ASK_SPEC_RENAME.format(name=texts.e(spec.name)), cancel_kb())


@router.message(AcademicForm.spec_rename, F.text)
async def spec_rename(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    try:
        await svc.academic.rename_specialization(user.telegram_id, data["spec_id"], message.text)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.clear()
    await message.answer(texts.AD_SPEC_RENAMED, reply_markup=kb((texts.BTN_BACK, Ad(a="sp", x=data["spec_id"])), HOME))


@router.callback_query(Ad.filter(F.a == "spd"))
async def spec_delete_confirm(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    try:
        spec = await svc.academic.specialization(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.AD_CONFIRM_DELETE_SPEC.format(name=texts.e(spec.name)),
                 kb((texts.BTN_CONFIRM, Ad(a="spdy", x=spec.id)), (texts.BTN_CANCEL, Ad(a="sp", x=spec.id))))


@router.callback_query(Ad.filter(F.a == "spdy"))
async def spec_delete(cb: CallbackQuery, callback_data: Ad, user: AppUser, svc: Services) -> None:
    try:
        spec = await svc.academic.specialization(callback_data.x)
        await svc.academic.delete_specialization(user.telegram_id, spec.id)
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.AD_SPEC_DELETED, kb((texts.BTN_BACK, Ad(a="yr", x=spec.year_id)), HOME))


# ───────────── subjects ─────────────
@router.callback_query(Ad.filter(F.a == "sby0"))
async def subjects_years(cb: CallbackQuery, state: FSMContext, svc: Services) -> None:
    await state.clear()
    rows = [(y.name, Ad(a="sby", x=y.id)) for y in await svc.academic.years()]
    await render(cb, texts.AD_SUBJECTS_YEAR, kb(*rows, (texts.BTN_BACK, Ad(a="acm"))))


@router.callback_query(Ad.filter(F.a == "sby"))
async def subjects_year(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    try:
        year = await svc.academic.year(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    if not year.requires_specialization:
        return await _semesters(cb, svc, year.id, None)
    specs = await svc.academic.specializations(year.id)
    back = (texts.BTN_BACK, Ad(a="sby0"))
    if not specs:
        return await render(cb, texts.AD_NO_SPECS, kb((texts.BTN_ADD_SPEC, Ad(a="spa", x=year.id)), back, HOME))
    rows = [(s.name, Ad(a="sbs", x=s.id)) for s in specs]
    await render(cb, texts.AD_SUBJECTS_SPEC.format(year=texts.e(year.name)), kb(*rows, back, HOME))


@router.callback_query(Ad.filter(F.a == "sbs"))
async def subjects_spec(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    try:
        spec = await svc.academic.specialization(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await _semesters(cb, svc, spec.year_id, spec.id)


async def _line(svc: Services, year_id: int, spec_id: int | None, semester: int | None = None) -> str:
    line = (await svc.academic.year(year_id)).name
    if spec_id:
        line += " • " + (await svc.academic.specialization(spec_id)).name
    if semester:
        line += " • " + texts.SEMESTER_NAMES[semester]
    return line


async def _semesters(event, svc: Services, year_id: int, spec_id: int | None) -> None:
    subjects = await svc.academic.subjects(year_id, spec_id)
    rows = [(f"{texts.SEMESTER_NAMES[sem]} ({sum(1 for s in subjects if s.semester == sem)})",
             Ad(a="sbm", x=year_id, y=spec_id or 0, p=sem)) for sem in SEMESTERS]
    back = Ad(a="sby", x=year_id) if spec_id else Ad(a="sby0")
    await render(event, texts.AD_SUBJECTS_SEMESTER.format(line=texts.e(await _line(svc, year_id, spec_id))),
                 kb(*rows, (texts.BTN_BACK, back), HOME))


@router.callback_query(Ad.filter(F.a == "sbm"))
async def subjects_semester(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    try:
        await _check_place(svc, callback_data.x, callback_data.y or None, callback_data.p)
    except DomainError as exc:
        return await show_error(cb, exc)
    await _subjects_list(cb, svc, callback_data.x, callback_data.y or None, callback_data.p)


async def _subjects_list(event, svc: Services, year_id: int, spec_id: int | None, semester: int) -> None:
    subjects = await svc.academic.subjects(year_id, spec_id, semester)
    line = await _line(svc, year_id, spec_id, semester)
    rows = [(("⚠️ " if not s.semester_confirmed else "") + f"{s.name} ({s.code})", Ad(a="sb", x=s.id))
            for s in subjects]
    back = Ad(a="sbs", x=spec_id) if spec_id else Ad(a="sby", x=year_id)
    await render(event, texts.AD_SUBJECTS_LIST.format(line=texts.e(line), n=len(subjects)),
                 kb(*rows, (texts.BTN_ADD_SUBJECT, Ad(a="sba", x=year_id, y=spec_id or 0, p=semester)),
                    (texts.BTN_BACK, back), HOME))


async def _check_place(svc: Services, year_id: int, spec_id: int | None, semester: int) -> None:
    """Validate a year / specialization / semester combination coming from callback data."""
    year = await svc.academic.year(year_id)
    if year.requires_specialization:
        if not spec_id or (await svc.academic.specialization(spec_id)).year_id != year.id:
            raise DomainError("specialization_required")
    elif spec_id:
        raise DomainError("specialization_not_allowed")
    if semester not in SEMESTERS:
        raise DomainError("invalid_semester")


@router.callback_query(Ad.filter(F.a == "sba"))
async def subject_add_start(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    spec_id, semester = callback_data.y or None, callback_data.p
    try:
        await _check_place(svc, callback_data.x, spec_id, semester)
        line = await _line(svc, callback_data.x, spec_id, semester)
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.set_state(AcademicForm.subject_name)
    await state.update_data(year_id=callback_data.x, spec_id=spec_id, semester=semester, line=line)
    await render(cb, texts.AD_ASK_SUBJECT_NAME.format(line=texts.e(line)), cancel_kb())


@router.message(AcademicForm.subject_name, F.text)
async def subject_add_name(message: Message, state: FSMContext) -> None:
    try:
        name = v.clean_text(message.text, min_len=2, max_len=150, code="invalid_subject_name")
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.update_data(name=name)
    await state.set_state(AcademicForm.subject_code)
    await message.answer(texts.AD_ASK_SUBJECT_CODE.format(name=texts.e(name)), reply_markup=cancel_kb())


@router.message(AcademicForm.subject_code, F.text)
async def subject_add_code(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    try:
        sid = await svc.academic.create_subject(user.telegram_id, data["year_id"], data["spec_id"], data["semester"],
                                                data["name"], message.text)
        subject = await svc.academic.subject(sid)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.clear()
    await message.answer(texts.AD_SUBJECT_CREATED.format(name=texts.e(subject.name), code=texts.e(subject.code),
                                                         line=texts.e(texts.subject_line(subject))),
                         reply_markup=kb((texts.BTN_ADD_SUBJECT, Ad(a="sba", x=subject.year_id,
                                                                    y=subject.specialization_id or 0,
                                                                    p=subject.semester)),
                                         (texts.BTN_BACK, Ad(a="sb", x=sid)), HOME))


@router.callback_query(Ad.filter(F.a == "sb"))
async def subject_view(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    try:
        s = await svc.academic.subject(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    stats = await svc.academic.subject_stats(s.id)
    back = Ad(a="sbm", x=s.year_id, y=s.specialization_id or 0, p=s.semester)
    text = texts.AD_SUBJECT_DETAILS.format(name=texts.e(s.name), code=texts.e(s.code),
                                           line=texts.e(texts.subject_line(s)), **stats)
    rows: list = [[(texts.BTN_EDIT_NAME, Ad(a="sbn", x=s.id)), (texts.BTN_EDIT_CODE, Ad(a="sbc", x=s.id))],
                  (texts.BTN_EDIT_SEMESTER, Ad(a="sbe", x=s.id))]
    if not s.semester_confirmed:
        text += texts.AD_SUBJECT_UNCONFIRMED_NOTE
        rows.insert(0, (texts.BTN_CONFIRM_SEMESTER, Ad(a="sbes", x=s.id, y=s.semester)))
    rows.append((texts.BTN_DELETE_SUBJECT, Ad(a="sbd", x=s.id)))
    await render(cb, text, kb(*rows, (texts.BTN_BACK, back), HOME))


@router.callback_query(Ad.filter(F.a == "sbe"))
async def subject_semester_pick(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    try:
        s = await svc.academic.subject(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    rows = [[(("✔️ " if sem == s.semester else "") + texts.SEMESTER_NAMES[sem], Ad(a="sbes", x=s.id, y=sem))
             for sem in SEMESTERS]]
    await render(cb, texts.AD_PICK_SEMESTER.format(name=texts.e(s.name), current=texts.SEMESTER_NAMES[s.semester]),
                 kb(*rows, (texts.BTN_BACK, Ad(a="sb", x=s.id))))


@router.callback_query(Ad.filter(F.a == "sbes"))
async def subject_semester_set(cb: CallbackQuery, callback_data: Ad, state: FSMContext, user: AppUser,
                               svc: Services) -> None:
    try:
        await svc.academic.update_subject(user.telegram_id, callback_data.x, "semester", callback_data.y)
    except DomainError as exc:
        return await show_error(cb, exc)
    await safe_answer(cb, texts.AD_SUBJECT_UPDATED)
    await subject_view(cb, Ad(a="sb", x=callback_data.x), state, svc)


@router.callback_query(Ad.filter(F.a.in_({"sbn", "sbc"})))
async def subject_edit_start(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    try:
        s = await svc.academic.subject(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.update_data(subject_id=s.id)
    if callback_data.a == "sbn":
        await state.set_state(AcademicForm.subject_new_name)
        text = texts.AD_ASK_SUBJECT_NEW_NAME.format(name=texts.e(s.name))
    else:
        await state.set_state(AcademicForm.subject_new_code)
        text = texts.AD_ASK_SUBJECT_NEW_CODE.format(name=texts.e(s.name), code=texts.e(s.code))
    await render(cb, text, cancel_kb())


@router.message(AcademicForm.subject_new_name, F.text)
@router.message(AcademicForm.subject_new_code, F.text)
async def subject_edit(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    field = "name" if await state.get_state() == AcademicForm.subject_new_name.state else "code"
    try:
        await svc.academic.update_subject(user.telegram_id, data["subject_id"], field, message.text)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.clear()
    await message.answer(texts.AD_SUBJECT_UPDATED,
                         reply_markup=kb((texts.BTN_BACK, Ad(a="sb", x=data["subject_id"])), HOME))


@router.callback_query(Ad.filter(F.a == "sbd"))
async def subject_delete_confirm(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    try:
        s = await svc.academic.subject(callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.AD_CONFIRM_DELETE_SUBJECT.format(name=texts.e(s.name), code=texts.e(s.code)),
                 kb((texts.BTN_CONFIRM, Ad(a="sbdy", x=s.id)), (texts.BTN_CANCEL, Ad(a="sb", x=s.id))))


@router.callback_query(Ad.filter(F.a == "sbdy"))
async def subject_delete(cb: CallbackQuery, callback_data: Ad, user: AppUser, svc: Services) -> None:
    try:
        s = await svc.academic.subject(callback_data.x)
        await svc.academic.delete_subject(user.telegram_id, s.id)
    except DomainError as exc:
        return await show_error(cb, exc)
    back = Ad(a="sbm", x=s.year_id, y=s.specialization_id or 0, p=s.semester)
    await render(cb, texts.AD_SUBJECT_DELETED, kb((texts.BTN_BACK, back), HOME))
