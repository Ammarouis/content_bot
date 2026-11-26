"""Admin: user management and student subject assignment."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Ad
from bot.handlers.utils import PER_PAGE, render, show_error
from bot.keyboards import CANCEL, HOME, cancel_kb, kb, paged
from bot.models import AppUser, Role
from bot.permissions import HasRole
from bot.services import validators as v
from bot.services.container import Services
from bot.services.errors import DomainError

router = Router(name="admin_users")
router.message.filter(HasRole(Role.ADMIN.value))
router.callback_query.filter(HasRole(Role.ADMIN.value))

ROLE_BY_IDX = {1: "admin", 2: "uploader", 3: "student"}
IDX_BY_ROLE = {v_: k for k, v_ in ROLE_BY_IDX.items()}


class UserForm(StatesGroup):
    tid = State()
    name = State()
    rename = State()


def _role_buttons(action: str, x: int = 0):
    return [(texts.ROLE_NAMES[r], Ad(a=action, x=x, y=i)) for i, r in ROLE_BY_IDX.items()]


@router.callback_query(Ad.filter(F.a == "um"))
async def users_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await render(cb, texts.AD_USERS_MENU, kb((texts.BTN_ADD_USER, Ad(a="ua")), (texts.BTN_LIST_USERS, Ad(a="uf")),
                                             HOME))


# ───────────── add user ─────────────
@router.callback_query(Ad.filter(F.a == "ua"))
async def add_start(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(UserForm.tid)
    await render(cb, texts.AD_ASK_TID, cancel_kb())


@router.message(UserForm.tid, F.text)
async def add_tid(message: Message, state: FSMContext, svc: Services) -> None:
    try:
        tid = v.telegram_id(message.text)
        existing = await svc.users.get(tid)
        if existing:
            return await message.answer(texts.error("user_exists"),
                                        reply_markup=kb((texts.user_label(existing), Ad(a="uv", x=tid)), CANCEL))
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.update_data(tid=tid)
    await state.set_state(UserForm.name)
    await message.answer(texts.AD_ASK_NAME.format(tid=tid), reply_markup=cancel_kb())


@router.message(UserForm.name, F.text)
async def add_name(message: Message, state: FSMContext) -> None:
    try:
        name = v.clean_text(message.text, min_len=2, max_len=100, code="invalid_name")
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.update_data(name=name)
    await state.set_state(None)
    await message.answer(texts.AD_ASK_ROLE.format(name=texts.e(name)), reply_markup=kb(_role_buttons("uar"), CANCEL))


@router.callback_query(Ad.filter(F.a == "uar"))
async def add_role(cb: CallbackQuery, callback_data: Ad, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    role = ROLE_BY_IDX.get(callback_data.y)
    if "tid" not in data or "name" not in data or not role:
        return await render(cb, texts.ST_SESSION_EXPIRED, kb((texts.BTN_ADD_USER, Ad(a="ua")), HOME))
    try:
        created = await svc.users.add(user.telegram_id, data["tid"], data["name"], role)
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.clear()
    text = texts.AD_USER_ADDED.format(name=texts.e(created.full_name), role=texts.ROLE_NAMES[role])
    rows = [(texts.BTN_ADD_USER, Ad(a="ua")), (texts.BTN_USERS, Ad(a="um")), HOME]
    if role == "student":
        text += texts.AD_USER_ADDED_STUDENT
        rows.insert(0, (texts.BTN_ASSIGN_SUBJECTS, Ad(a="us", x=created.telegram_id)))
    await render(cb, text, kb(*rows))


# ───────────── list & details ─────────────
@router.callback_query(Ad.filter(F.a == "uf"))
async def users_filter(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = [(texts.BTN_ALL, Ad(a="ul", x=0))] + [(texts.ROLE_NAMES_PLURAL[r], Ad(a="ul", x=i))
                                                 for i, r in ROLE_BY_IDX.items()]
    await render(cb, texts.AD_USERS_FILTER, kb(*rows, (texts.BTN_BACK, Ad(a="um"))))


@router.callback_query(Ad.filter(F.a == "ul"))
async def users_list(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    role = ROLE_BY_IDX.get(callback_data.x)
    users, total = await svc.users.list(role, callback_data.p, PER_PAGE)
    title = texts.ROLE_NAMES_PLURAL[role] if role else texts.BTN_ALL
    if not total:
        return await render(cb, texts.EMPTY_LIST, kb((texts.BTN_BACK, Ad(a="uf"))))
    await render(cb, texts.AD_USERS_LIST.format(title=title, total=total),
                 paged(users, lambda u: (texts.user_label(u), Ad(a="uv", x=u.telegram_id)), callback_data.p, total,
                       PER_PAGE, lambda p: Ad(a="ul", x=callback_data.x, p=p), [(texts.BTN_BACK, Ad(a="uf"))]))


async def _user_card(event, svc: Services, tid: int) -> None:
    target = await svc.users.get(tid)
    if not target:
        return await show_error(event, DomainError("user_not_found"))
    extra = ""
    if target.role == "student":
        extra += texts.AD_USER_SUBJECTS_COUNT.format(n=len(await svc.users.student_subject_ids(tid)))
    protected = tid in svc.config.admin_ids
    if protected:
        extra += texts.AD_USER_PROTECTED
    text = texts.AD_USER_DETAILS.format(name=texts.e(target.full_name), tid=tid, role=texts.ROLE_NAMES[target.role],
                                        created=texts.fmt_time(target.created_at), extra=extra)
    rows = []
    if target.role == "student":
        rows.append((texts.BTN_ASSIGN_SUBJECTS, Ad(a="us", x=tid)))
    rows.append((texts.BTN_RENAME, Ad(a="urn", x=tid)))
    if not protected:
        rows.append([(texts.BTN_CHANGE_ROLE, Ad(a="ucr", x=tid)), (texts.BTN_REMOVE_USER, Ad(a="urm", x=tid))])
    rows.append((texts.BTN_BACK, Ad(a="ul", x=IDX_BY_ROLE[target.role])))
    await render(event, text, kb(*rows, HOME))


@router.callback_query(Ad.filter(F.a == "uv"))
async def user_view(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    await _user_card(cb, svc, callback_data.x)


@router.callback_query(Ad.filter(F.a == "ucr"))
async def role_pick(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    target = await svc.users.get(callback_data.x)
    if not target:
        return await show_error(cb, DomainError("user_not_found"))
    text = texts.AD_PICK_ROLE.format(name=texts.e(target.full_name))
    if target.role == "student":
        text += texts.AD_ROLE_CHANGE_NOTE
    buttons = [b for b in _role_buttons("ucrs", target.telegram_id) if ROLE_BY_IDX[b[1].y] != target.role]
    await render(cb, text, kb(buttons, (texts.BTN_BACK, Ad(a="uv", x=target.telegram_id))))


@router.callback_query(Ad.filter(F.a == "ucrs"))
async def role_set(cb: CallbackQuery, callback_data: Ad, user: AppUser, svc: Services) -> None:
    role = ROLE_BY_IDX.get(callback_data.y)
    try:
        updated = await svc.users.change_role(user.telegram_id, callback_data.x, role or "")
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.AD_ROLE_CHANGED.format(role=texts.ROLE_NAMES[updated.role]),
                 kb((texts.BTN_BACK, Ad(a="uv", x=updated.telegram_id)), HOME))


@router.callback_query(Ad.filter(F.a == "urn"))
async def rename_start(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    target = await svc.users.get(callback_data.x)
    if not target:
        return await show_error(cb, DomainError("user_not_found"))
    await state.set_state(UserForm.rename)
    await state.update_data(target=target.telegram_id)
    await render(cb, texts.AD_ASK_RENAME.format(name=texts.e(target.full_name)), cancel_kb())


@router.message(UserForm.rename, F.text)
async def rename_do(message: Message, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    try:
        await svc.users.rename(user.telegram_id, data["target"], message.text)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.clear()
    await message.answer(texts.AD_RENAMED, reply_markup=kb((texts.BTN_BACK, Ad(a="uv", x=data["target"])), HOME))


@router.callback_query(Ad.filter(F.a == "urm"))
async def remove_confirm(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    target = await svc.users.get(callback_data.x)
    if not target:
        return await show_error(cb, DomainError("user_not_found"))
    await render(cb, texts.AD_CONFIRM_REMOVE.format(name=texts.e(target.full_name), tid=target.telegram_id,
                                                    role=texts.ROLE_NAMES[target.role]),
                 kb((texts.BTN_CONFIRM_REMOVE, Ad(a="urmy", x=target.telegram_id)),
                    (texts.BTN_CANCEL, Ad(a="uv", x=target.telegram_id))))


@router.callback_query(Ad.filter(F.a == "urmy"))
async def remove_do(cb: CallbackQuery, callback_data: Ad, user: AppUser, svc: Services) -> None:
    try:
        await svc.users.remove(user.telegram_id, callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await render(cb, texts.AD_REMOVED, kb((texts.BTN_LIST_USERS, Ad(a="uf")), HOME))


# ───────────── student subject assignment ─────────────
async def _student(cb: CallbackQuery, svc: Services, tid: int) -> AppUser | None:
    target = await svc.users.get(tid)
    if not target or target.role != "student":
        await show_error(cb, DomainError("not_a_student"))
        return None
    return target


@router.callback_query(Ad.filter(F.a == "us"))
async def assign_years(cb: CallbackQuery, callback_data: Ad, state: FSMContext, svc: Services) -> None:
    await state.clear()
    target = await _student(cb, svc, callback_data.x)
    if not target:
        return
    years = await svc.academic.years()
    current = await svc.users.student_subjects(target.telegram_id)
    text = texts.AD_ASSIGN_TITLE.format(name=texts.e(target.full_name))
    if current:
        text += texts.AD_ASSIGN_CURRENT.format(
            subjects="\n".join(f"• {texts.e(s.name)} (<code>{texts.e(s.code)}</code>)" for s in current))
    rows = [(y.name, Ad(a="usy", x=target.telegram_id, y=y.id)) for y in years]
    await render(cb, text, kb(*rows, (texts.BTN_BACK, Ad(a="uv", x=target.telegram_id)), HOME))


@router.callback_query(Ad.filter(F.a == "usy"))
async def assign_year(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    target = await _student(cb, svc, callback_data.x)
    if not target:
        return
    try:
        year = await svc.academic.year(callback_data.y)
    except DomainError as exc:
        return await show_error(cb, exc)
    if not year.requires_specialization:
        return await _assign_subjects(cb, svc, target, year.id, None)
    specs = await svc.academic.specializations(year.id)
    back = (texts.BTN_BACK, Ad(a="us", x=target.telegram_id))
    if not specs:
        return await render(cb, texts.AD_NO_SPECS, kb(back, HOME))
    rows = [(s.name, Ad(a="uss", x=target.telegram_id, y=s.id)) for s in specs]
    await render(cb, texts.AD_ASSIGN_SPEC.format(name=texts.e(target.full_name), year=texts.e(year.name)),
                 kb(*rows, back, HOME))


@router.callback_query(Ad.filter(F.a == "uss"))
async def assign_spec(cb: CallbackQuery, callback_data: Ad, svc: Services) -> None:
    target = await _student(cb, svc, callback_data.x)
    if not target:
        return
    try:
        spec = await svc.academic.specialization(callback_data.y)
    except DomainError as exc:
        return await show_error(cb, exc)
    await _assign_subjects(cb, svc, target, spec.year_id, spec.id)


async def _assign_subjects(cb: CallbackQuery, svc: Services, target: AppUser, year_id: int,
                           spec_id: int | None) -> None:
    subjects = await svc.academic.subjects(year_id, spec_id)
    assigned = await svc.users.student_subject_ids(target.telegram_id)
    year = await svc.academic.year(year_id)
    line = year.name
    back = Ad(a="usy", x=target.telegram_id, y=year_id) if spec_id else Ad(a="us", x=target.telegram_id)
    if spec_id:
        line += " • " + (await svc.academic.specialization(spec_id)).name
    if not subjects:
        return await render(cb, texts.AD_NO_SUBJECTS, kb((texts.BTN_BACK, back), HOME))
    rows = [(f"{'✅' if s.id in assigned else '⬜️'} {s.name} ({s.code}) • {texts.SEMESTER_NAMES[s.semester]}",
             Ad(a="ust", x=target.telegram_id, y=s.id)) for s in subjects]
    await render(cb, texts.AD_ASSIGN_SUBJECTS.format(name=texts.e(target.full_name), line=texts.e(line)),
                 kb(*rows, (texts.BTN_BACK, back), HOME))


@router.callback_query(Ad.filter(F.a == "ust"))
async def assign_toggle(cb: CallbackQuery, callback_data: Ad, user: AppUser, svc: Services) -> None:
    try:
        await svc.users.toggle_assignment(user.telegram_id, callback_data.x, callback_data.y)
        subject = await svc.academic.subject(callback_data.y)
    except DomainError as exc:
        return await show_error(cb, exc)
    target = await _student(cb, svc, callback_data.x)
    if target:
        await _assign_subjects(cb, svc, target, subject.year_id, subject.specialization_id)
