"""Permanent student content protection (bot/policy.py): verified on real outgoing Bot API requests."""
from __future__ import annotations

import pytest
from aiogram.methods import (
    CopyMessage, CopyMessages, DeleteMessage, EditMessageText, ForwardMessage, ForwardMessages, SendAnimation,
    SendAudio, SendContact, SendDice, SendDocument, SendLocation, SendMediaGroup, SendMessage, SendPhoto, SendPoll,
    SendSticker, SendVenue, SendVideo, SendVideoNote, SendVoice,
)

from bot import texts
from bot.callbacks import Ad, Nav, St
from bot.db import repositories as repo
from bot.db.database import Database
from bot.models import FileInfo
from bot.policy import StudentProtectionMiddleware, protect_for_role, protect_for_stage
from tests.conftest import ADMIN, CH, STRANGER, STUDENT, STUDENT2, UPLOADER

PDF = FileInfo("PDF1", "UPDF1", "a.pdf", 100)
TEX = FileInfo("TEX1", "UTEX1", "a.tex", 100)

PROTECTABLE = (SendMessage, SendDocument, SendPhoto, SendVideo, SendAudio, SendVoice, SendAnimation, SendVideoNote,
               SendMediaGroup, SendSticker, SendLocation, SendVenue, SendContact, SendPoll, SendDice, CopyMessage,
               CopyMessages, ForwardMessage, ForwardMessages)


async def _submit(env, number=1, student=STUDENT):
    return await env.svc.content.submit(student, env.subject_id, "lecture", number, PDF, None, TEX)


async def _files(env, cid):
    return {f.kind: f for f in (await env.svc.content.get(cid)).files}


def _sent_to(env, chat_id, kind=None):
    return [m for m in env.tg.calls if getattr(m, "chat_id", None) == chat_id
            and "protect_content" in type(m).model_fields and (kind is None or isinstance(m, kind))]


async def _make_outdated(env, cid, stage_flags: dict[str, int]):
    """Simulate files posted under the old configurable policy (protected/unprotected the 'wrong' way)."""
    async with env.svc.db.tx() as c:
        for kind, flag in stage_flags.items():
            await c.execute("UPDATE content_files SET protect_requested = ? WHERE content_id = ? AND kind = ?",
                            (flag, cid, kind))


# ═════════════ the rule itself ═════════════
def test_rule_is_hardcoded():
    assert protect_for_role("student") is True
    assert protect_for_role("uploader") is False and protect_for_role("admin") is False
    assert protect_for_role(None) is False
    assert protect_for_stage("approved") is True and protect_for_stage("temp") is False


# ═════════════ every Telegram send method, every recipient ═════════════
@pytest.mark.parametrize("method_cls", PROTECTABLE, ids=lambda c: c.__name__)
async def test_middleware_sets_flag_for_every_protectable_method(seeded, method_cls):
    env = seeded
    mw = StudentProtectionMiddleware(env.svc.db, CH, frozenset({ADMIN}))
    seen = []

    async def make_request(bot, method):
        seen.append(method.protect_content)
        return None

    # caller asks for the opposite of the rule each time; the rule must win
    cases = {STUDENT: True, CH.approved_pdf: True, CH.approved_tex: True,
             UPLOADER: False, ADMIN: False, CH.temp_pdf: False, CH.temp_tex: False, STRANGER: False}
    for chat_id, expected in cases.items():
        method = method_cls.model_construct(chat_id=chat_id, protect_content=not expected)
        await mw(make_request, env.bot, method)
        assert seen[-1] is expected, (method_cls.__name__, chat_id)


async def test_methods_without_protection_field_untouched(seeded):
    env = seeded
    mw = StudentProtectionMiddleware(env.svc.db, CH, frozenset({ADMIN}))
    for method in (EditMessageText.model_construct(chat_id=STUDENT, message_id=1, text="x"),
                   DeleteMessage.model_construct(chat_id=STUDENT, message_id=1)):
        async def make_request(bot, m):
            return "ok"
        assert await mw(make_request, env.bot, method) == "ok"
        assert "protect_content" not in method.model_fields_set


async def test_real_bot_calls_are_protected_for_students_only(seeded):
    """Direct Bot API calls (any future code path) — even an explicit protect_content=False cannot reach a student."""
    bot, tg = seeded.bot, seeded.tg
    m = await bot.send_message(STUDENT, "x", protect_content=False)
    assert m.has_protected_content is True
    m = await bot.send_document(STUDENT, "FILE", protect_content=False)
    assert m.has_protected_content is True
    src = await bot.send_document(CH.temp_pdf, "FILE")
    assert not src.has_protected_content
    await bot.copy_message(STUDENT, CH.temp_pdf, src.message_id, protect_content=False)
    assert tg.of(CopyMessage)[-1].protect_content is True
    for uid in (ADMIN, UPLOADER):
        m = await bot.send_document(uid, "FILE", protect_content=True)
        assert not m.has_protected_content                  # admins / uploaders stay unrestricted
        m = await bot.send_message(uid, "x", protect_content=True)
        assert not m.has_protected_content
    m = await bot.send_document(CH.approved_pdf, "FILE", protect_content=False)
    assert m.has_protected_content is True


# ═════════════ workflows ═════════════
async def test_all_student_screens_and_notifications_are_protected(seeded):
    env, tg = seeded, seeded.tg
    await env.text(STUDENT, "/start")
    await env.click(STUDENT, St(a="up"))
    await env.click(STUDENT, St(a="ups", x=env.subject_id))
    await env.click(STUDENT, env.button(STUDENT, texts.TYPE_NAMES["lecture"]))
    await env.pick_number(STUDENT, 1)
    await env.text(STUDENT, "hello")                         # wrong input → new message
    await env.doc(STUDENT, "a.pdf", "application/pdf")
    await env.doc(STUDENT, "a.tex")
    await env.click(STUDENT, St(a="send"))
    cid = (await env.svc.content.pending(0, 10))[0][0].id
    await env.svc.content.reject(UPLOADER, cid, "سبب الرفض")   # rejection notification to the student
    await env.svc.content.resubmit(STUDENT, cid, PDF, TEX)
    await env.svc.content.approve(UPLOADER, cid)             # approval notification to the student
    await env.click(STUDENT, Nav(to="support"))

    student_msgs = _sent_to(env, STUDENT)
    assert len(student_msgs) >= 4
    assert all(m.protect_content is True for m in student_msgs)
    assert all(info.get("has_protected_content") for (c, _), info in tg.messages.items() if c == STUDENT)
    staff_msgs = _sent_to(env, UPLOADER) + _sent_to(env, ADMIN)
    assert staff_msgs and all(m.protect_content is False for m in staff_msgs)


async def test_channels_and_reviewer_previews(seeded):
    env = seeded
    c = await _submit(env)
    temp = _sent_to(env, CH.temp_pdf, SendDocument) + _sent_to(env, CH.temp_tex, SendDocument)
    assert len(temp) == 2 and all(m.protect_content is False for m in temp)
    assert all(not f.protect_requested and f.protected is False for f in (await _files(env, c.id)).values())
    for viewer in (UPLOADER, ADMIN):
        await env.svc.content.send_preview(viewer, c.id)
        assert all(m.protect_content is False for m in _sent_to(env, viewer, SendDocument))
    await env.svc.content.approve(UPLOADER, c.id)
    published = _sent_to(env, CH.approved_pdf, SendDocument) + _sent_to(env, CH.approved_tex, SendDocument)
    assert len(published) == 2 and all(m.protect_content is True for m in published)
    files = await _files(env, c.id)
    assert all(f.stage == "approved" and f.protect_requested and f.protected for f in files.values())  # verified


async def test_role_changes_apply_immediately(seeded):
    env, bot = seeded, seeded.bot
    assert (await bot.send_message(STUDENT2, "x")).has_protected_content
    await env.click(ADMIN, Ad(a="ucrs", x=STUDENT2, y=2))    # student → uploader
    assert not (await bot.send_message(STUDENT2, "x")).has_protected_content
    await env.click(ADMIN, Ad(a="ucrs", x=UPLOADER, y=3))    # uploader → student
    assert (await bot.send_message(UPLOADER, "x")).has_protected_content


async def test_lookup_failure_fails_closed(seeded, monkeypatch):
    env, bot = seeded, seeded.bot

    async def broken(_tid):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(env.svc.db, "role_of", broken)
    assert (await bot.send_message(UPLOADER, "x")).has_protected_content          # unknown → protected
    assert not (await bot.send_message(ADMIN, "x")).has_protected_content         # bootstrap admins known by config


# ═════════════ cannot be disabled ═════════════
async def test_no_protection_controls_in_dashboard(seeded):
    env = seeded
    await env.click(ADMIN, Ad(a="sm"))
    labels = " ".join(env.buttons(ADMIN))
    assert "حماية" not in labels and "إيقاف" not in labels and "تفعيل" not in labels
    for forged in (Ad(a="pr"), Ad(a="prt", x=0), Ad(a="pra", x=2)):          # old v2 buttons / forged callbacks
        await env.click(ADMIN, forged)
    assert env.alerts().count(texts.STALE_BUTTON) == 3
    assert not hasattr(env.svc.settings, "set_enabled") and not hasattr(env.svc.settings, "protection")
    assert (await env.bot.send_message(STUDENT, "x")).has_protected_content


async def test_database_settings_cannot_disable_protection(seeded):
    env = seeded
    async with env.svc.db.tx() as c:
        for key, value in (("protection_enabled", "0"), ("protection_audience", "uploaders"),
                           ("protect_content", "0"), ("student_protection", "off")):
            await repo.set_setting(c, key, value, ADMIN)
    c1 = await _submit(env)
    await env.svc.content.approve(UPLOADER, c1.id)
    assert all(f.protected for f in (await _files(env, c1.id)).values())
    assert (await env.bot.send_message(STUDENT, "x")).has_protected_content
    assert not (await env.bot.send_message(UPLOADER, "x")).has_protected_content


# ═════════════ existing content follows the rule ═════════════
async def test_existing_posts_are_republished_to_match_the_rule(seeded):
    env, tg = seeded, seeded.tg
    approved = await _submit(env, 1)
    await env.svc.content.approve(UPLOADER, approved.id)
    pending = await _submit(env, 2)
    await _make_outdated(env, approved.id, {"pdf": 0, "tex": 0})   # e.g. published while v2 protection was off
    await _make_outdated(env, pending.id, {"pdf": 1, "tex": 1})    # e.g. v2 audience "uploaders"
    old = [(f.chat_id, f.message_id) for cid in (approved.id, pending.id) for f in (await _files(env, cid)).values()]
    assert (await env.svc.protection.stats())["outdated"] == 4

    before = len(tg.of(SendDocument))
    await env.svc.cleanup.tick()                                     # background worker
    assert len(tg.of(SendDocument)) - before == 4
    assert all(m.disable_notification for m in tg.of(SendDocument)[-4:])   # silent re-posts
    assert all(f.protect_requested and f.protected for f in (await _files(env, approved.id)).values())
    assert all(not f.protect_requested and f.protected is False for f in (await _files(env, pending.id)).values())
    assert all(k not in tg.messages for k in old)                    # old posts removed
    assert len(tg.documents_in(CH.approved_pdf)) == 1 and len(tg.documents_in(CH.temp_pdf)) == 1
    assert (await env.svc.protection.stats())["outdated"] == 0
    before = len(tg.calls)
    await env.svc.cleanup.tick()                                     # nothing left: no Telegram traffic
    assert not [m for m in tg.calls[before:] if isinstance(m, SendDocument)]


async def test_republish_failure_is_retried_and_reported(seeded):
    env = seeded
    c = await _submit(env)
    await env.svc.content.approve(UPLOADER, c.id)
    await _make_outdated(env, c.id, {"pdf": 0, "tex": 0})
    env.tg.fail_when(lambda m: isinstance(m, SendDocument) and m.chat_id == CH.approved_tex)
    await env.svc.cleanup.tick()
    files = await _files(env, c.id)
    assert files["pdf"].protect_requested and not files["tex"].protect_requested
    await env.click(ADMIN, Ad(a="ch"))
    assert texts.AD_PROTECTION_PENDING.format(n=1).strip() in env.last_text(ADMIN)
    env.tg.clear_failures()
    await env.svc.cleanup.tick()
    assert (await _files(env, c.id))["tex"].protected is True
    await env.click(ADMIN, Ad(a="ch"))
    assert "قيد إعادة النشر" not in env.last_text(ADMIN)


async def test_unconfirmed_protection_is_reported(seeded):
    env = seeded
    env.tg.ignore_protection = True
    c = await _submit(env)
    await env.svc.content.approve(UPLOADER, c.id)
    assert all(f.protect_requested and f.protected is False for f in (await _files(env, c.id)).values())
    await env.click(ADMIN, Ad(a="ch"))
    assert texts.AD_PROTECTION_NOT_HONOURED.format(n=2).strip() in env.last_text(ADMIN)


async def test_republish_never_orphans_messages_on_concurrent_delete(seeded):
    env, tg = seeded, seeded.tg
    c = await _submit(env)
    await env.svc.content.approve(UPLOADER, c.id)
    await _make_outdated(env, c.id, {"pdf": 0, "tex": 0})
    real_send = env.svc.gateway.send_document
    fired = False

    async def send_then_delete(*args, **kwargs):
        nonlocal fired
        sent = await real_send(*args, **kwargs)
        if not fired:
            fired = True
            await env.svc.content.delete(ADMIN, c.id)
        return sent

    env.svc.gateway.send_document = send_then_delete
    await env.svc.protection.sync()
    env.svc.gateway.send_document = real_send
    await env.svc.cleanup.process_due()
    assert tg.documents_in(CH.approved_pdf) == [] and tg.documents_in(CH.approved_tex) == []
    async with env.svc.db.read() as conn:
        assert await repo._scalar(conn, "SELECT COUNT(*) FROM cleanup_queue WHERE status IN ('held','pending')") == 0


async def test_republish_discarded_when_files_change_meanwhile(seeded):
    env, tg = seeded, seeded.tg
    c = await _submit(env)
    await env.svc.content.reject(UPLOADER, c.id, "سبب")
    await _make_outdated(env, c.id, {"pdf": 1, "tex": 1})
    real_send = env.svc.gateway.send_document
    fired = False

    async def send_then_resubmit(*args, **kwargs):
        nonlocal fired
        sent = await real_send(*args, **kwargs)
        if not fired:
            fired = True
            env.svc.gateway.send_document = real_send
            await env.svc.content.resubmit(STUDENT, c.id, FileInfo("PDF2", "U2", "b.pdf", 1),
                                           FileInfo("TEX2", "U3", "b.tex", 1))
            env.svc.gateway.send_document = send_then_resubmit
        return sent

    env.svc.gateway.send_document = send_then_resubmit
    await env.svc.protection.sync()
    env.svc.gateway.send_document = real_send
    await env.svc.cleanup.process_due()
    files = await _files(env, c.id)
    assert files["pdf"].file_id == "PDF2" and files["tex"].file_id == "TEX2"
    assert all(not f.protect_requested for f in files.values())
    for ch, f in ((CH.temp_pdf, files["pdf"]), (CH.temp_tex, files["tex"])):
        assert [m["document"]["file_id"] for m in tg.documents_in(ch)] == [f.file_id]
    async with env.svc.db.read() as conn:
        assert await repo._scalar(conn, "SELECT COUNT(*) FROM cleanup_queue WHERE status IN ('held','pending')") == 0


# ═════════════ migration v2 → v3 ═════════════
async def test_migration_removes_protection_settings(tmp_path):
    path = str(tmp_path / "bot.db")
    db = Database(path)
    await db.connect()
    async with db.tx() as c:
        for key, value in (("protection_enabled", "0"), ("protection_audience", "uploaders"),
                           ("protection_sync_pending", "1"), ("support_username", "Help_Desk")):
            await repo.set_setting(c, key, value, None)
    await db.conn.execute("PRAGMA user_version = 2")
    await db.close()

    db = Database(path)
    await db.connect()
    try:
        async with db.read() as c:
            assert await repo._scalar(c, "PRAGMA user_version") == 3
            assert dict(await repo._all(c, "SELECT key, value FROM settings")) == {"support_username": "Help_Desk"}
    finally:
        await db.close()
