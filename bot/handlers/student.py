"""Student interface: subjects, recent submissions, submission wizard, rejected content & resubmission."""
from __future__ import annotations

import secrets

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.callbacks import Nav, St
from bot.handlers.utils import PER_PAGE, file_info, render, safe_answer, show_error
from bot.keyboards import CANCEL, HOME, cancel_kb, kb, paged
from bot.models import AppUser, FileInfo, Role, number_category
from bot.permissions import HasRole
from bot.services import validators as v
from bot.services.container import Services
from bot.services.errors import DomainError

router = Router(name="student")
router.message.filter(HasRole(Role.STUDENT.value))
router.callback_query.filter(HasRole(Role.STUDENT.value))

TYPES = ("lecture", "session")
PAGE_SIZE = 20           # numbers per page
ROW_SIZE = 5             # buttons per row
MAX_NUMBER = 9999        # matches the CHECK constraint on contents.number
MAX_PAGE = (MAX_NUMBER - 1) // PAGE_SIZE


class SubmitFlow(StatesGroup):
    number = State()
    pdf = State()
    skip_reason = State()
    tex = State()
    confirm = State()


class ResubmitFlow(StatesGroup):
    pdf = State()
    tex = State()
    confirm = State()


BACK_HOME = kb(HOME)


# ───────────── my subjects ─────────────
@router.callback_query(St.filter(F.a == "subs"))
async def my_subjects(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    subjects = await svc.users.student_subjects(user.telegram_id)
    if not subjects:
        return await render(cb, texts.ST_NO_SUBJECTS, BACK_HOME)
    rows = [(f"{s.name} ({s.code})", St(a="sub", x=s.id)) for s in subjects]
    await render(cb, texts.ST_SUBJECTS_TITLE, kb(*rows, HOME))


@router.callback_query(St.filter(F.a == "sub"))
async def subject_info(cb: CallbackQuery, callback_data: St, user: AppUser, svc: Services) -> None:
    try:
        s = await svc.content.assigned_subject(user.telegram_id, callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    summary = await svc.content.subject_summary(s.id)
    text = texts.ST_SUBJECT_INFO.format(
        name=texts.e(s.name), code=texts.e(s.code), line=texts.e(texts.subject_line(s)),
        lectures=texts.subject_summary_block(summary.get("lecture")),
        sessions=texts.subject_summary_block(summary.get("session")))
    await render(cb, text, kb((texts.BTN_UPLOAD, St(a="ups", x=s.id)), (texts.BTN_BACK, St(a="subs")), HOME))


# ───────────── recent ─────────────
@router.callback_query(St.filter(F.a == "recent"))
async def recent(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    items = await svc.content.student_recent(user.telegram_id, 5)
    await render(cb, texts.recent_list(items) if items else texts.ST_RECENT_EMPTY, BACK_HOME)


# ───────────── submission wizard ─────────────
@router.callback_query(St.filter(F.a == "up"))
async def upload_start(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    await state.clear()
    subjects = await svc.users.student_subjects(user.telegram_id)
    if not subjects:
        return await render(cb, texts.ST_NO_SUBJECTS, BACK_HOME)
    rows = [(f"{s.name} ({s.code})", St(a="ups", x=s.id)) for s in subjects]
    await render(cb, texts.ST_PICK_SUBJECT, kb(*rows, HOME))


@router.callback_query(St.filter(F.a == "ups"))
async def upload_subject(cb: CallbackQuery, callback_data: St, state: FSMContext, user: AppUser,
                         svc: Services) -> None:
    try:
        s = await svc.content.assigned_subject(user.telegram_id, callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.clear()
    nonce = secrets.randbelow(30000) + 1   # ties every button of this wizard to this wizard only
    label = f"{s.name} ({s.code})"
    await state.update_data(subject_id=s.id, subject=label, nonce=nonce)
    await render(cb, texts.ST_PICK_TYPE.format(subject=texts.e(label)),
                 kb([(texts.TYPE_NAMES["lecture"], St(a="upt", x=0, n=nonce)),
                     (texts.TYPE_NAMES["session"], St(a="upt", x=1, n=nonce))], CANCEL))


async def _wizard(cb: CallbackQuery, callback_data: St, state: FSMContext, *required: str) -> dict | None:
    """Return wizard data if the pressed button belongs to the active wizard; otherwise reject it as stale."""
    data = await state.get_data()
    if not data.get("nonce") or data["nonce"] != callback_data.n or any(k not in data for k in required):
        await safe_answer(cb, texts.ST_SESSION_EXPIRED, alert=True)
        return None
    return data


@router.callback_query(St.filter(F.a == "upt"))
async def upload_type(cb: CallbackQuery, callback_data: St, state: FSMContext, svc: Services) -> None:
    data = await _wizard(cb, callback_data, state, "subject_id")
    if data is None:
        return
    if callback_data.x not in (0, 1):
        return await safe_answer(cb, texts.error("invalid_type"), alert=True)
    await state.update_data(ctype=TYPES[callback_data.x])
    await state.set_state(SubmitFlow.number)
    await _show_picker(cb, svc, await state.get_data(), 0)


# ───────────── number picker ─────────────
async def _show_picker(cb: CallbackQuery | Message, svc: Services, data: dict, page: int,
                       notice: str | None = None) -> None:
    """Render one page of numbers with their *current* status (read live from the database every time)."""
    page = max(0, min(page, MAX_PAGE))
    statuses = await svc.content.number_statuses(data["subject_id"], data["ctype"])
    nonce = data["nonce"]
    start, end = page * PAGE_SIZE + 1, min((page + 1) * PAGE_SIZE, MAX_NUMBER)
    buttons = []
    for number in range(start, end + 1):
        category = number_category(statuses.get(number))
        action = "nb" if category == "available" else "nbx"   # occupied numbers can only show an alert
        buttons.append((texts.number_button(number, category), St(a=action, x=number, n=nonce)))
    rows: list = [buttons[i:i + ROW_SIZE] for i in range(0, len(buttons), ROW_SIZE)]
    nav = []
    if page > 0:
        nav.append((texts.BTN_LESS, St(a="nbp", p=page - 1, n=nonce)))
    if page < MAX_PAGE:
        nav.append((texts.BTN_MORE, St(a="nbp", p=page + 1, n=nonce)))
    rows.append(nav)
    rows.append([(texts.BTN_REFRESH, St(a="nbp", p=page, n=nonce)),
                 (texts.BTN_BACK, St(a="ups", x=data["subject_id"]))])
    rows.append(CANCEL)
    text = texts.ST_ASK_NUMBER.format(subject=texts.e(data["subject"]), ctype=texts.TYPE_NAMES[data["ctype"]],
                                      start=start, end=end, legend=texts.NUMBER_LEGEND)
    if isinstance(cb, Message):
        if notice:
            text = f"{notice}\n\n{text}"
        return await render(cb, text, kb(*rows))
    await render(cb, text, kb(*rows))
    if notice:
        await safe_answer(cb, notice, alert=True)


@router.callback_query(St.filter(F.a == "nbp"), SubmitFlow.number)
async def picker_page(cb: CallbackQuery, callback_data: St, state: FSMContext, svc: Services) -> None:
    data = await _wizard(cb, callback_data, state, "subject_id", "ctype")
    if data is not None:
        await state.update_data(page=callback_data.p)
        await _show_picker(cb, svc, data, callback_data.p)


@router.callback_query(St.filter(F.a.in_({"nb", "nbx"})), SubmitFlow.number)
async def picker_select(cb: CallbackQuery, callback_data: St, state: FSMContext, svc: Services) -> None:
    data = await _wizard(cb, callback_data, state, "subject_id", "ctype")
    if data is None:
        return
    number, page = callback_data.x, data.get("page", 0)
    if not (1 <= number <= MAX_NUMBER):
        return await safe_answer(cb, texts.error("invalid_number"), alert=True)
    # server-side check: the keyboard may be outdated, and button styling is never trusted
    current = (await svc.content.number_statuses(data["subject_id"], data["ctype"])).get(number)
    category = number_category(current)
    if category != "available":
        return await _show_picker(cb, svc, data, page,
                                  texts.error("number_taken", number=number, state=texts.NUMBER_STATE[category]))
    if callback_data.a == "nbx":   # was occupied when drawn, has been freed since (deleted by admin)
        return await _show_picker(cb, svc, data, page, texts.ST_NUMBER_REFRESHED)
    await state.update_data(number=number)
    await state.set_state(SubmitFlow.pdf)
    await render(cb, texts.ST_ASK_PDF.format(title=texts.e(_title({**data, "number": number}))),
                 kb((texts.BTN_SKIP_PDF, St(a="skip")), CANCEL))


def _title(data: dict) -> str:
    return f"{data['subject']} • {texts.TYPE_NAMES[data['ctype']]} {data['number']}"


@router.message(SubmitFlow.pdf, F.document)
async def upload_pdf(message: Message, state: FSMContext, svc: Services) -> None:
    doc = message.document
    try:
        v.document(doc.file_name, doc.mime_type, doc.file_size, "pdf", svc.config.max_pdf_bytes)
    except DomainError as exc:
        return await show_error(message, exc, kb((texts.BTN_SKIP_PDF, St(a="skip")), CANCEL))
    await state.update_data(pdf=file_info(message).to_dict(), skip_reason=None)
    await state.set_state(SubmitFlow.tex)
    await message.answer(texts.ST_ASK_TEX.format(title=texts.e(_title(await state.get_data()))), reply_markup=cancel_kb())


@router.callback_query(St.filter(F.a == "skip"), SubmitFlow.pdf)
async def upload_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SubmitFlow.skip_reason)
    await render(cb, texts.ST_ASK_SKIP_REASON, cancel_kb())


@router.message(SubmitFlow.skip_reason, F.text)
async def upload_skip_reason(message: Message, state: FSMContext) -> None:
    try:
        reason = v.clean_text(message.text, min_len=5, max_len=500, code="invalid_skip_reason")
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.update_data(pdf=None, skip_reason=reason)
    await state.set_state(SubmitFlow.tex)
    await message.answer(texts.ST_ASK_TEX.format(title=texts.e(_title(await state.get_data()))), reply_markup=cancel_kb())


@router.message(SubmitFlow.tex, F.document)
async def upload_tex(message: Message, state: FSMContext, svc: Services) -> None:
    doc = message.document
    try:
        v.document(doc.file_name, doc.mime_type, doc.file_size, "tex", svc.config.max_tex_bytes)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.update_data(tex=file_info(message).to_dict())
    await state.set_state(SubmitFlow.confirm)
    data = await state.get_data()
    pdf = FileInfo.from_dict(data.get("pdf"))
    pdf_line = (texts.ST_SUMMARY_PDF.format(name=texts.e(pdf.file_name)) if pdf
                else texts.ST_SUMMARY_NO_PDF.format(reason=texts.e(data.get("skip_reason"))))
    await message.answer(
        texts.ST_SUMMARY.format(subject=texts.e(data["subject"]), ctype=texts.TYPE_NAMES[data["ctype"]],
                                number=data["number"], pdf_line=pdf_line, tex=texts.e(doc.file_name)),
        reply_markup=kb((texts.BTN_SUBMIT, St(a="send")), CANCEL))


@router.callback_query(St.filter(F.a == "send"), SubmitFlow.confirm)
async def upload_send(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    await state.clear()  # prevents double submission by repeated taps
    await render(cb, texts.ST_SENDING)
    try:
        content = await svc.content.submit(
            user.telegram_id, data["subject_id"], data["ctype"], data["number"],
            FileInfo.from_dict(data.get("pdf")), data.get("skip_reason"), FileInfo.from_dict(data["tex"]))
    except DomainError as exc:
        markup = kb((texts.BTN_SUPPORT, Nav(to="support")), HOME) if exc.code == "duplicate_content" else BACK_HOME
        return await render(cb, texts.error(exc.code, **exc.params), markup)
    await render(cb, texts.ST_SUBMITTED.format(title=texts.e(texts.content_title(content))), BACK_HOME)


# ───────────── rejected & resubmission ─────────────
@router.callback_query(St.filter(F.a == "rej"))
async def rejected_list(cb: CallbackQuery, callback_data: St, state: FSMContext, user: AppUser,
                        svc: Services) -> None:
    await state.clear()
    items, total = await svc.content.student_rejected(user.telegram_id, callback_data.p, PER_PAGE)
    if not total:
        return await render(cb, texts.ST_REJECTED_EMPTY, BACK_HOME)
    await render(cb, texts.ST_REJECTED_TITLE,
                 paged(items, lambda c: (f"❌ {c.subject_name} • {texts.TYPE_NAMES[c.content_type]} {c.number}",
                                         St(a="rj", x=c.id)),
                       callback_data.p, total, PER_PAGE, lambda p: St(a="rej", p=p), [HOME]))


@router.callback_query(St.filter(F.a == "rj"))
async def rejected_item(cb: CallbackQuery, callback_data: St, state: FSMContext, user: AppUser,
                        svc: Services) -> None:
    await state.clear()
    try:
        c = await svc.content.get_for_student(user.telegram_id, callback_data.x)
    except DomainError as exc:
        return await show_error(cb, exc)
    details = texts.content_details(c, show_student=False, show_files=False)
    if c.status != "rejected":
        return await render(cb, details, kb((texts.BTN_BACK, St(a="rej")), HOME))
    await render(cb, texts.ST_REJECTED_ITEM.format(details=details),
                 kb((texts.BTN_ATTACH_NEW, St(a="resub", x=c.id)), (texts.BTN_BACK, St(a="rej")), HOME))


@router.callback_query(St.filter(F.a == "resub"))
async def resubmit_start(cb: CallbackQuery, callback_data: St, state: FSMContext, user: AppUser,
                         svc: Services) -> None:
    try:
        c = await svc.content.get_for_student(user.telegram_id, callback_data.x)
        if c.status != "rejected":
            raise DomainError("not_rejected")
    except DomainError as exc:
        return await show_error(cb, exc)
    await state.clear()
    title = texts.content_title(c)
    await state.update_data(content_id=c.id, title=title)
    await state.set_state(ResubmitFlow.pdf)
    await render(cb, texts.ST_RESUB_PDF.format(title=texts.e(title)), cancel_kb())


@router.message(ResubmitFlow.pdf, F.document)
async def resubmit_pdf(message: Message, state: FSMContext, svc: Services) -> None:
    doc = message.document
    try:
        v.document(doc.file_name, doc.mime_type, doc.file_size, "pdf", svc.config.max_pdf_bytes)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.update_data(pdf=file_info(message).to_dict())
    await state.set_state(ResubmitFlow.tex)
    data = await state.get_data()
    await message.answer(texts.ST_RESUB_TEX.format(title=texts.e(data["title"])), reply_markup=cancel_kb())


@router.message(ResubmitFlow.tex, F.document)
async def resubmit_tex(message: Message, state: FSMContext, svc: Services) -> None:
    doc = message.document
    try:
        v.document(doc.file_name, doc.mime_type, doc.file_size, "tex", svc.config.max_tex_bytes)
    except DomainError as exc:
        return await show_error(message, exc, cancel_kb())
    await state.update_data(tex=file_info(message).to_dict())
    await state.set_state(ResubmitFlow.confirm)
    data = await state.get_data()
    await message.answer(
        texts.ST_RESUB_SUMMARY.format(title=texts.e(data["title"]), pdf=texts.e(data["pdf"]["file_name"]),
                                      tex=texts.e(doc.file_name)),
        reply_markup=kb((texts.BTN_SUBMIT, St(a="resend")), CANCEL))


@router.callback_query(St.filter(F.a == "resend"), ResubmitFlow.confirm)
async def resubmit_send(cb: CallbackQuery, state: FSMContext, user: AppUser, svc: Services) -> None:
    data = await state.get_data()
    await state.clear()
    await render(cb, texts.ST_SENDING)
    try:
        content = await svc.content.resubmit(user.telegram_id, data["content_id"], FileInfo.from_dict(data["pdf"]),
                                             FileInfo.from_dict(data["tex"]))
    except DomainError as exc:
        return await render(cb, texts.error(exc.code, **exc.params), BACK_HOME)
    await render(cb, texts.ST_RESUBMITTED.format(title=texts.e(texts.content_title(content))), BACK_HOME)


# ───────────── wrong input inside wizard steps ─────────────
@router.message(SubmitFlow.pdf)
async def expect_pdf(message: Message) -> None:
    await message.answer(texts.ST_EXPECT_PDF, reply_markup=kb((texts.BTN_SKIP_PDF, St(a="skip")), CANCEL))


@router.message(ResubmitFlow.pdf)
async def expect_pdf_mandatory(message: Message) -> None:
    await message.answer(texts.ST_EXPECT_PDF_MANDATORY, reply_markup=cancel_kb())


@router.message(SubmitFlow.tex)
@router.message(ResubmitFlow.tex)
async def expect_tex(message: Message) -> None:
    await message.answer(texts.ST_EXPECT_TEX, reply_markup=cancel_kb())


@router.message(SubmitFlow.number)
async def expect_number_button(message: Message, state: FSMContext, svc: Services) -> None:
    # numbers are chosen from buttons only; show the picker again (fresh statuses) right below
    data = await state.get_data()
    if not all(k in data for k in ("subject_id", "ctype", "nonce")):
        return await message.answer(texts.ST_SESSION_EXPIRED, reply_markup=BACK_HOME)
    await _show_picker(message, svc, data, data.get("page", 0), texts.ST_EXPECT_NUMBER_BUTTON)


@router.message(SubmitFlow.skip_reason)
async def expect_text(message: Message) -> None:
    await message.answer(texts.ST_EXPECT_TEXT, reply_markup=cancel_kb())


@router.callback_query(St.filter(F.a.in_({"send", "resend", "skip", "nb", "nbx", "nbp"})))
async def stale_step(cb: CallbackQuery) -> None:
    await safe_answer(cb, texts.ST_SESSION_EXPIRED, alert=True)
