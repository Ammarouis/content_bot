"""End-to-end tests: updates are fed through the real dispatcher, middlewares, routers and services."""
from __future__ import annotations

from aiogram.methods import SendDocument, SendMessage

from bot import texts
from bot.callbacks import Ad, Nav, Rv, St
from bot.db import repositories as repo
from tests.conftest import ADMIN, CH, STRANGER, STUDENT, STUDENT2, UPLOADER


async def _content_row(env, cid):
    async with env.svc.db.read() as c:
        return await repo.get_content(c, cid)


async def _start_wizard(env, uid=STUDENT, ctype=0, subject_id=None):
    await env.click(uid, St(a="up"))
    await env.click(uid, St(a="ups", x=subject_id or env.subject_id))
    await env.click(uid, env.button(uid, texts.TYPE_NAMES[("lecture", "session")[ctype]]))


async def _submit(env, uid=STUDENT, number=3, ctype=0, pdf=True, reason=None, subject_id=None):
    await _start_wizard(env, uid, ctype, subject_id)
    await env.pick_number(uid, int(number))
    if pdf:
        await env.doc(uid, "lecture.pdf", "application/pdf")
    else:
        await env.click(uid, St(a="skip"))
        await env.text(uid, reason)
    await env.doc(uid, "lecture.tex")
    await env.click(uid, St(a="send"))


# ───────────── access control ─────────────
async def test_unauthorized_user_gets_arabic_denial(env):
    await env.text(STRANGER, "/start")
    assert "لا تملك صلاحية استخدام هذا البوت" in env.last_text(STRANGER)
    assert str(STRANGER) in env.last_text(STRANGER)
    await env.click(STRANGER, Ad(a="um"))
    assert texts.UNAUTHORIZED_ALERT in env.alerts()


async def test_role_menus(seeded):
    env = seeded
    await env.text(ADMIN, "/start")
    assert set(env.buttons(ADMIN)) >= {texts.BTN_USERS, texts.BTN_ACADEMIC, texts.BTN_CONTENT, texts.BTN_SETTINGS}
    await env.text(STUDENT, "/start")
    assert set(env.buttons(STUDENT)) == {texts.BTN_MY_SUBJECTS, texts.BTN_RECENT, texts.BTN_UPLOAD,
                                         texts.BTN_REJECTED, texts.BTN_SUPPORT}
    await env.text(UPLOADER, "/start")
    labels = list(env.buttons(UPLOADER))
    assert any(texts.BTN_PENDING in t for t in labels) and texts.BTN_APPROVED in labels
    assert not any(texts.BTN_USERS in t for t in labels)


async def test_forged_callbacks_are_blocked_server_side(seeded):
    env = seeded
    before = len(env.outputs(STUDENT))
    await env.click(STUDENT, Ad(a="um"))                      # admin area
    await env.click(STUDENT, Ad(a="urmy", x=UPLOADER))       # try to delete a user
    await env.click(STUDENT, Rv(a="apy", x=1))               # try to approve
    await env.click(UPLOADER, St(a="up"))                     # uploader in student area
    await env.click(UPLOADER, Ad(a="cdy", x=1))              # uploader tries deletion
    assert len(env.outputs(STUDENT)) == before
    assert env.alerts().count(texts.STALE_BUTTON) == 5
    assert await env.svc.users.get(UPLOADER) is not None


async def test_free_text_outside_flow(seeded):
    await seeded.text(STUDENT, "hello")
    assert seeded.last_text(STUDENT) == texts.USE_BUTTONS


# ───────────── admin management through the UI ─────────────
async def test_admin_adds_user_creates_subject_and_assigns(env):
    await env.click(ADMIN, Ad(a="ua"))
    await env.text(ADMIN, "abc")
    assert "غير صالح" in env.last_text(ADMIN)
    await env.text(ADMIN, str(STUDENT))
    await env.text(ADMIN, "  أحمد   علي ")
    await env.click(ADMIN, Ad(a="uar", y=3))
    assert "تمت إضافة المستخدم" in env.last_text(ADMIN)
    u = await env.svc.users.get(STUDENT)
    assert u.role == "student" and u.full_name == "أحمد علي"

    # year 4 requires specialization: add one, then a subject inside it
    await env.click(ADMIN, Ad(a="spa", x=4))
    await env.text(ADMIN, "هندسة البرمجيات")
    spec = (await env.svc.academic.specializations(4))[0]
    await env.click(ADMIN, Ad(a="sba", x=4, y=0, p=2))
    assert any("الاختصاص" in a for a in env.alerts())   # spec missing -> refused (forged callback)
    # navigate like a user: subjects → year 4 → specialization → second semester → add
    await env.click(ADMIN, Ad(a="sby0"))
    await env.click(ADMIN, env.button(ADMIN, "السنة الرابعة"))
    await env.click(ADMIN, env.button(ADMIN, "هندسة البرمجيات"))
    await env.click(ADMIN, env.button(ADMIN, texts.SEMESTER_NAMES[2]))
    await env.click(ADMIN, env.button(ADMIN, texts.BTN_ADD_SUBJECT))
    assert "الفصل الثاني" in env.last_text(ADMIN) and "هندسة البرمجيات" in env.last_text(ADMIN)
    await env.text(ADMIN, "هندسة البرمجيات 2")
    await env.text(ADMIN, "se-402")
    assert "رمز المادة غير صالح" in env.last_text(ADMIN)
    await env.text(ADMIN, "se402")
    assert "تم إنشاء المادة" in env.last_text(ADMIN)
    subject = await env.svc.academic.subject_by_code("SE402")
    assert subject.specialization_id == spec.id and subject.semester == 2 and subject.semester_confirmed

    await env.click(ADMIN, Ad(a="ust", x=STUDENT, y=subject.id))
    assert any(t.startswith("✅") and "هندسة البرمجيات 2" in t for t in env.buttons(ADMIN))
    assert subject.id in await env.svc.users.student_subject_ids(STUDENT)


async def test_admin_user_guards(seeded):
    env = seeded
    await env.click(ADMIN, Ad(a="urmy", x=ADMIN))
    assert any("مدير النظام الأساسي" in a for a in env.alerts())
    await env.click(ADMIN, Ad(a="ucrs", x=STUDENT, y=2))       # student -> uploader clears subjects
    assert (await env.svc.users.get(STUDENT)).role == "uploader"
    assert await env.svc.users.student_subject_ids(STUDENT) == set()
    await env.click(ADMIN, Ad(a="urmy", x=STUDENT2))
    assert await env.svc.users.get(STUDENT2) is None
    await env.text(STUDENT2, "/start")
    assert "لا تملك صلاحية" in env.last_text(STUDENT2)


# ───────────── full lifecycle ─────────────
async def test_full_content_lifecycle(seeded):
    env, tg = seeded, seeded.tg

    # student cannot use an unassigned subject
    other = await env.svc.academic.create_subject(ADMIN, 2, None, 1, "رياضيات", "MATH2")
    await env.click(STUDENT, St(a="ups", x=other))
    assert any("غير مسندة" in a for a in env.alerts())

    # 1) submission with PDF + TEX
    await _submit(env, number=3)
    assert "تم إرسال المحتوى للمراجعة" in env.last_text(STUDENT)
    items, total = await env.svc.content.pending(0, 10)
    assert total == 1
    cid = items[0].id
    c = await _content_row(env, cid)
    assert c.status == "pending" and c.number == 3
    assert {(f.kind, f.stage, f.chat_id) for f in c.files} == {("pdf", "temp", CH.temp_pdf), ("tex", "temp", CH.temp_tex)}
    assert any(isinstance(m, SendMessage) and m.chat_id == UPLOADER and "محتوى جديد" in m.text for m in tg.calls)

    # 2) the taken number is shown as pending and cannot be selected
    await _start_wizard(env)
    label, action = env.picker(STUDENT)[3]
    assert label.startswith("🟡") and action == "nbx"
    await env.pick_number(STUDENT, 3)
    assert any("الرقم 3 غير متاح" in a and "قيد المراجعة" in a for a in env.alerts())
    await env.click(STUDENT, Nav(to="cancel"))

    # 3) uploader previews files (tracked) and rejects with mandatory reason
    await env.click(UPLOADER, Rv(a="files", x=cid))
    previews = [m for m in tg.of(SendDocument) if m.chat_id == UPLOADER]
    assert len(previews) == 2
    await env.click(UPLOADER, Rv(a="rj", x=cid))
    await env.text(UPLOADER, "x")
    assert "سبب الرفض إلزامي" in env.last_text(UPLOADER)
    await env.text(UPLOADER, "المعادلات في الصفحة 3 غير مكتملة")
    c = await _content_row(env, cid)
    assert c.status == "rejected" and c.rejection_reason.startswith("المعادلات")
    assert "تم رفض المحتوى الخاص بك" in env.last_text(STUDENT)
    assert not [k for k in tg.in_chat(UPLOADER) if "copied_from" in tg.messages[k]]   # review copies removed

    # 4) student sees rejected item and resubmits (PDF mandatory, no skip)
    await env.click(STUDENT, St(a="rej"))
    await env.click(STUDENT, St(a="rj", x=cid))
    assert "المعادلات في الصفحة 3" in env.last_text(STUDENT)
    assert texts.BTN_ATTACH_NEW in env.buttons(STUDENT)
    old_temp = {(f.chat_id, f.message_id) for f in c.files}
    await env.click(STUDENT, St(a="resub", x=cid))
    await env.doc(STUDENT, "new.tex")
    assert "PDF" in env.last_text(STUDENT)                  # TEX refused at PDF step
    await env.doc(STUDENT, "new.pdf", "application/pdf")
    await env.doc(STUDENT, "new.tex")
    await env.click(STUDENT, St(a="resend"))
    assert "تمت إعادة إرسال" in env.last_text(STUDENT)
    c = await _content_row(env, cid)
    assert c.status == "pending" and c.id == cid
    assert c.rejection_reason is not None                    # kept until next decision
    assert all(k not in tg.messages for k in old_temp)       # old temp files deleted
    assert {f.file_name for f in c.files} == {"new.pdf", "new.tex"}

    # 5) approval moves files to approved channels and removes temp copies
    temp_now = {(f.chat_id, f.message_id) for f in c.files}
    await env.click(UPLOADER, Rv(a="ap", x=cid))
    await env.click(UPLOADER, Rv(a="apy", x=cid))
    assert "تم اعتماد المحتوى بنجاح" in env.last_text(UPLOADER)
    c = await _content_row(env, cid)
    assert c.status == "approved" and c.rejection_reason is None
    assert {(f.kind, f.stage, f.chat_id) for f in c.files} == {("pdf", "approved", CH.approved_pdf),
                                                               ("tex", "approved", CH.approved_tex)}
    assert all(k not in tg.messages for k in temp_now)
    assert tg.in_chat(CH.temp_pdf) == [] and tg.in_chat(CH.temp_tex) == []
    assert "تم اعتماد المحتوى الخاص بك" in env.last_text(STUDENT)

    # approved section lists it
    await env.click(UPLOADER, Rv(a="ay"))
    await env.click(UPLOADER, env.button(UPLOADER, "السنة الأولى (1)"))
    await env.click(UPLOADER, env.button(UPLOADER, "الفصل الأول (1)"))
    assert any("برمجة 1" in t and "(1)" in t for t in env.buttons(UPLOADER))

    # double approval is refused
    await env.click(UPLOADER, Rv(a="apy", x=cid))
    assert "لم يعد هذا المحتوى بانتظار المراجعة" in env.last_text(UPLOADER)

    # 6) admin search → confirm → delete
    await env.click(ADMIN, Rv(a="files", x=cid))             # admin preview copies are tracked as well
    await env.click(ADMIN, Ad(a="cs"))
    await env.text(ADMIN, "cs101")
    await env.click(ADMIN, Ad(a="cst", x=env.subject_id, y=1))
    await env.text(ADMIN, "3")
    await env.click(ADMIN, Rv(a="av", x=cid))
    await env.click(ADMIN, Ad(a="cd", x=cid))
    assert "تأكيد الحذف النهائي" in env.last_text(ADMIN) and "CS101" in env.last_text(ADMIN)
    assert await _content_row(env, cid) is not None           # nothing deleted before confirmation
    await env.click(ADMIN, Ad(a="cdy", x=cid))
    assert "تم الحذف بالكامل" in env.last_text(ADMIN)
    assert await _content_row(env, cid) is None
    assert tg.in_chat(CH.approved_pdf) == [] and tg.in_chat(CH.approved_tex) == []
    assert tg.documents_in(ADMIN) == []                                                 # preview copies removed

    # 7) number is free again
    await _submit(env, number=3)
    assert "تم إرسال المحتوى للمراجعة" in env.last_text(STUDENT)


async def test_skip_pdf_requires_reason_and_is_stored(seeded):
    env = seeded
    await _start_wizard(env, ctype=1)
    await env.text(STUDENT, "7")                                # typing is not accepted; buttons only
    assert texts.ST_EXPECT_NUMBER_BUTTON in env.last_text(STUDENT)
    await env.pick_number(STUDENT, 7)
    await env.doc(STUDENT, "notes.docx")
    assert "ليس ملف PDF" in env.last_text(STUDENT)
    await env.click(STUDENT, St(a="skip"))
    await env.text(STUDENT, "لا")
    assert "سبب واضح" in env.last_text(STUDENT)
    await env.text(STUDENT, "الجلسة عملية بدون شرائح")
    await env.doc(STUDENT, "s.pdf", "application/pdf")
    assert ".tex" in env.last_text(STUDENT)
    await env.doc(STUDENT, "s.tex")
    assert "لم يُرفق" in env.last_text(STUDENT)
    await env.click(STUDENT, St(a="send"))
    items, _ = await env.svc.content.pending(0, 10)
    c = await _content_row(env, items[0].id)
    assert c.content_type == "session" and c.pdf_skip_reason == "الجلسة عملية بدون شرائح"
    assert [f.kind for f in c.files] == ["tex"]
    # repeated tap on an already submitted wizard does nothing
    await env.click(STUDENT, St(a="send"))
    assert (await env.svc.content.pending(0, 10))[1] == 1


async def test_student_views(seeded):
    env = seeded
    await _submit(env, number=1)
    await _submit(env, number=2, ctype=1, pdf=False, reason="سبب كاف للتخطي")
    await env.click(STUDENT, St(a="recent"))
    assert "محاضرة 1" in env.last_text(STUDENT) and "جلسة 2" in env.last_text(STUDENT)
    await env.click(STUDENT, St(a="sub", x=env.subject_id))
    assert "قيد المراجعة: 1" in env.last_text(STUDENT)
    await env.click(STUDENT, St(a="rej"))
    assert env.last_text(STUDENT) == texts.ST_REJECTED_EMPTY
    # other student cannot open someone else's record
    await env.click(STUDENT2, St(a="rj", x=1))
    assert any("غير موجود" in a for a in env.alerts())


async def test_settings_support_and_protection(seeded):
    env = seeded
    await env.click(STUDENT, Nav(to="support"))
    assert texts.SUPPORT_NOT_SET == env.last_text(STUDENT)
    await env.click(ADMIN, Ad(a="sue"))
    await env.text(ADMIN, "bad name!")
    assert "غير صالح" in env.last_text(ADMIN)
    await env.text(ADMIN, "https://t.me/ITGenix_Support")
    await env.click(UPLOADER, Nav(to="support"))
    assert "@ITGenix_Support" in env.last_text(UPLOADER)
    assert env.buttons(UPLOADER)[texts.BTN_CONTACT_SUPPORT] == "https://t.me/ITGenix_Support"

    await env.click(ADMIN, Ad(a="ch"))
    assert "قناة PDF المعتمدة" in env.last_text(ADMIN) and "صلاحية الحذف: نعم" in env.last_text(ADMIN)
    assert "دائمة ولا يمكن إيقافها" in env.last_text(ADMIN)
