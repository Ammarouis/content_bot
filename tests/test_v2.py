"""v2 acceptance tests: unified protection, semester hierarchy, number picker, migration and permissions."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from aiogram.methods import SendDocument

from bot import texts
from bot.callbacks import Ad, Nav, Rv, St
from bot.db import repositories as repo
from bot.db.database import SCHEMA_VERSION, Database
from bot.models import FileInfo
from bot.services.errors import DomainError
from tests.conftest import ADMIN, CH, STUDENT, STUDENT2, UPLOADER

PDF = FileInfo("PDF1", "UPDF1", "a.pdf", 100)
TEX = FileInfo("TEX1", "UTEX1", "a.tex", 100)
FIXTURE_V1 = Path(__file__).parent / "fixtures" / "schema_v1.sql"


async def _submit(env, number=1, ctype="lecture", student=STUDENT, subject=None):
    return await env.svc.content.submit(student, subject or env.subject_id, ctype, number, PDF, None, TEX)


async def _files(env, cid):
    return {f.kind: f for f in (await env.svc.content.get(cid)).files}


def _docs_to(env, chat_id):
    return [m for m in env.tg.of(SendDocument) if m.chat_id == chat_id]


async def _open_picker(env, uid=STUDENT, ctype=0, subject=None):
    await env.click(uid, St(a="up"))
    await env.click(uid, St(a="ups", x=subject or env.subject_id))
    await env.click(uid, env.button(uid, texts.TYPE_NAMES[("lecture", "session")[ctype]]))


def _nonce(env, uid=STUDENT) -> int:
    for data in env.buttons(uid).values():
        if data and data.startswith("s:nb"):
            return St.unpack(data).n
    raise AssertionError("picker not shown")


# ═════════════ 2/3. semesters, subject creation, approved navigation ═════════════
async def test_subject_creation_semester_and_specialization_rule(seeded):
    env, a = seeded, seeded.svc.academic
    with pytest.raises(DomainError) as ei:
        await a.create_subject(ADMIN, 1, None, 3, "مادة", "XX1")
    assert ei.value.code == "invalid_semester"
    with pytest.raises(DomainError) as ei:
        await a.create_subject(ADMIN, 4, None, 1, "مادة", "XX1")
    assert ei.value.code == "specialization_required"
    spec = await a.add_specialization(ADMIN, 5, "ذكاء صنعي")
    with pytest.raises(DomainError):
        await a.create_subject(ADMIN, 2, spec, 1, "مادة", "XX1")
    with pytest.raises(DomainError):
        await a.create_subject(UPLOADER, 1, None, 1, "مادة", "XX1")
    sid = await a.create_subject(ADMIN, 5, spec, 2, "تعلم آلي", "ml501")
    s = await a.subject(sid)
    assert (s.year_id, s.specialization_id, s.semester, s.semester_confirmed, s.code) == (5, spec, 2, True, "ML501")
    assert [x.id for x in await a.subjects(5, spec, 2)] == [sid] and await a.subjects(5, spec, 1) == []
    # forged callback for adding a subject without semester / with a wrong year is refused server-side
    await env.click(ADMIN, Ad(a="sba", x=1, y=0, p=0))
    await env.click(ADMIN, Ad(a="sba", x=1, y=spec, p=1))
    assert sum("الفصل الدراسي غير صالح" in x or "اختصاص" in x for x in env.alerts()) == 2


async def test_admin_edits_semester(seeded):
    env = seeded
    await env.click(ADMIN, Ad(a="sb", x=env.subject_id))
    await env.click(ADMIN, env.button(ADMIN, texts.BTN_EDIT_SEMESTER))
    await env.click(ADMIN, env.button(ADMIN, texts.SEMESTER_NAMES[2]))
    assert (await env.svc.academic.subject(env.subject_id)).semester == 2
    assert texts.SEMESTER_NAMES[2] in env.last_text(ADMIN)
    await env.click(UPLOADER, Ad(a="sbes", x=env.subject_id, y=1))       # RBAC
    assert (await env.svc.academic.subject(env.subject_id)).semester == 2


async def test_approved_navigation_full_hierarchy(seeded):
    env, a = seeded, seeded.svc.academic
    spec = await a.add_specialization(ADMIN, 4, "شبكات")
    net = await a.create_subject(ADMIN, 4, spec, 2, "شبكات 2", "NET402")
    await env.svc.users.toggle_assignment(ADMIN, STUDENT, net)
    lec = await _submit(env, 1, subject=net)
    ses = await _submit(env, 1, "session", subject=net)
    await _submit(env, 2, subject=net)                     # pending: must not be counted as approved
    for c in (lec, ses):
        await env.svc.content.approve(UPLOADER, c.id)

    for uid in (ADMIN, UPLOADER):
        await env.click(uid, Rv(a="ay"))
        assert "السنة الرابعة (2)" in env.buttons(uid) and "السنة الأولى (0)" in env.buttons(uid)
        await env.click(uid, env.button(uid, "السنة الرابعة (2)"))
        await env.click(uid, env.button(uid, "شبكات (2)"))
        assert "الفصل الثاني (2)" in env.buttons(uid) and "الفصل الأول (0)" in env.buttons(uid)
        await env.click(uid, env.button(uid, "الفصل الثاني (2)"))
        await env.click(uid, env.button(uid, "شبكات 2 (NET402) (2)"))
        assert "المحاضرات (1)" in env.buttons(uid) and "الجلسات (1)" in env.buttons(uid)
        await env.click(uid, env.button(uid, "المحاضرات (1)"))
        items = [d for d in env.buttons(uid).values() if d and d.startswith("r:av:")]
        assert len(items) == 1
        await env.click(uid, items[0])
        assert "NET402" in env.last_text(uid)
        await env.click(uid, env.button(uid, texts.BTN_BACK))           # back to the list
        await env.click(uid, env.button(uid, texts.BTN_BACK))           # back to types
        await env.click(uid, env.button(uid, texts.BTN_BACK))           # back to subjects
        await env.click(uid, env.button(uid, texts.BTN_BACK))           # back to semesters
        assert "الفصل الثاني (2)" in env.buttons(uid)

    # year without specializations goes straight to semesters
    await env.click(ADMIN, Rv(a="ayy", x=1))
    assert "الفصل الأول (0)" in env.buttons(ADMIN)
    # students cannot browse the review area
    await env.click(STUDENT, Rv(a="ay"))
    await env.click(STUDENT, Rv(a="atl", x=net, y=1))
    assert env.alerts().count(texts.STALE_BUTTON) == 2


async def test_admin_content_menu_uses_shared_hierarchy(seeded):
    env = seeded
    await env.click(ADMIN, Ad(a="cm"))
    await env.click(ADMIN, env.button(ADMIN, texts.BTN_APPROVED_CONTENT))
    assert any(t.startswith("السنة الأولى") for t in env.buttons(ADMIN))


# ═════════════ 4. number picker ═════════════
async def test_picker_paging_and_more(seeded):
    env = seeded
    await _open_picker(env)
    assert sorted(env.picker(STUDENT)) == list(range(1, 21))
    assert texts.BTN_LESS not in env.buttons(STUDENT)
    await env.click(STUDENT, env.button(STUDENT, texts.BTN_MORE))
    assert sorted(env.picker(STUDENT)) == list(range(21, 41))
    await env.click(STUDENT, env.button(STUDENT, texts.BTN_MORE))
    assert sorted(env.picker(STUDENT)) == list(range(41, 61))
    await env.click(STUDENT, env.button(STUDENT, texts.BTN_LESS))
    assert sorted(env.picker(STUDENT)) == list(range(21, 41))
    assert "21" in env.last_text(STUDENT) and "40" in env.last_text(STUDENT)
    await env.pick_number(STUDENT, 25)
    assert "25" in env.last_text(STUDENT) and texts.BTN_SKIP_PDF in env.buttons(STUDENT)


async def test_picker_status_colours_and_independent_types(seeded):
    env = seeded
    pending = await _submit(env, 1)
    approved = await _submit(env, 2)
    rejected = await _submit(env, 3)
    await env.svc.content.approve(UPLOADER, approved.id)
    await env.svc.content.reject(UPLOADER, rejected.id, "سبب الرفض")
    await _open_picker(env)
    p = env.picker(STUDENT)
    assert p[1] == ("🟡1", "nbx") and p[2] == ("🟢2", "nbx") and p[3] == ("🔴3", "nbx") and p[4] == ("4", "nb")
    assert "🟢" in env.last_text(STUDENT) and "🟡" in env.last_text(STUDENT)      # legend
    await _open_picker(env, ctype=1)                        # sessions are numbered independently
    assert all(action == "nb" for _, action in env.picker(STUDENT).values())
    assert pending.number == 1


async def test_occupied_and_forged_numbers_are_blocked(seeded):
    env = seeded
    await _submit(env, 1)
    await _open_picker(env)
    nonce = _nonce(env)
    await env.click(STUDENT, St(a="nbx", x=1, n=nonce))
    await env.click(STUDENT, St(a="nb", x=1, n=nonce))      # forged "available" callback for a taken number
    assert env.alerts().count(texts.error("number_taken", number=1, state="قيد المراجعة")) == 2
    await env.click(STUDENT, St(a="nb", x=0, n=nonce))
    await env.click(STUDENT, St(a="nb", x=10000, n=nonce))
    assert env.alerts().count(texts.error("invalid_number")) == 2
    await env.click(STUDENT, St(a="nb", x=5, n=nonce + 1))  # keyboard of another wizard
    assert texts.ST_SESSION_EXPIRED in env.alerts()
    with pytest.raises(DomainError) as ei:
        await _submit(env, 1)                               # service + UNIQUE constraint
    assert ei.value.code == "duplicate_content"


async def test_stale_keyboard_after_restart_of_wizard(seeded):
    env = seeded
    await _open_picker(env)
    old = _nonce(env)
    await _open_picker(env)                                 # new wizard (e.g. pressed «رفع محتوى جديد» again)
    await env.click(STUDENT, St(a="nb", x=5, n=old))
    assert texts.ST_SESSION_EXPIRED in env.alerts()
    await env.click(STUDENT, Nav(to="cancel"))
    await env.click(STUDENT, St(a="nb", x=5, n=_nonce(env) if env.picker(STUDENT) else old))
    assert env.alerts().count(texts.ST_SESSION_EXPIRED) == 2


async def test_number_taken_while_choosing_and_concurrent_submissions(seeded):
    env = seeded
    await env.svc.users.toggle_assignment(ADMIN, STUDENT2, env.subject_id)
    await _open_picker(env, STUDENT)
    await _open_picker(env, STUDENT2)
    assert env.picker(STUDENT2)[5][1] == "nb"
    await env.pick_number(STUDENT, 5)                       # both pick 5 before anyone submits
    await env.pick_number(STUDENT2, 5)
    for uid in (STUDENT, STUDENT2):
        await env.doc(uid, "a.pdf", "application/pdf")
        await env.doc(uid, "a.tex")
    await env.click(STUDENT, St(a="send"))
    await env.click(STUDENT2, St(a="send"))
    assert "تم إرسال المحتوى للمراجعة" in env.last_text(STUDENT)
    assert "مرفوع مسبقاً" in env.last_text(STUDENT2)
    items, total = await env.svc.content.pending(0, 10)
    assert total == 1 and items[0].student_id == STUDENT
    assert env.tg.documents_in(CH.temp_pdf).__len__() == 1  # the loser's upload was rolled back

    # stale picker: number taken after the keyboard was drawn
    await _open_picker(env, STUDENT2)
    await _submit(env, 6)
    await env.pick_number(STUDENT2, 6)
    assert texts.error("number_taken", number=6, state="قيد المراجعة") in env.alerts()
    assert env.picker(STUDENT2)[6][0] == "🟡6"               # keyboard refreshed

    # true concurrency at service level: exactly one wins
    results = await asyncio.gather(*[_submit(env, 9, student=s) for s in (STUDENT, STUDENT2, STUDENT)],
                                   return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1


async def test_picker_refreshes_after_every_transition(seeded):
    env = seeded

    async def label(n=1):
        await _open_picker(env)
        return env.picker(STUDENT)[n][0]

    c = await _submit(env, 1)
    assert await label() == "🟡1"
    await env.svc.content.reject(UPLOADER, c.id, "سبب أول")
    assert await label() == "🔴1"
    await env.svc.content.resubmit(STUDENT, c.id, PDF, TEX)
    assert await label() == "🟡1"
    await env.svc.content.approve(UPLOADER, c.id)
    assert await label() == "🟢1"
    await env.svc.content.delete(ADMIN, c.id)
    assert await label() == "1"
    # a number freed while the keyboard was open can be chosen after refresh
    c2 = await _submit(env, 2)
    await _open_picker(env)
    await env.svc.content.delete(ADMIN, c2.id)
    await env.pick_number(STUDENT, 2)
    assert texts.ST_NUMBER_REFRESHED in env.alerts() and env.picker(STUDENT)[2] == ("2", "nb")
    await env.pick_number(STUDENT, 2)
    assert texts.BTN_SKIP_PDF in env.buttons(STUDENT)


# ═════════════ 5. rejected workflow ═════════════
async def test_repeated_rejection_then_approval(seeded):
    env = seeded
    c = await _submit(env, 4)
    await env.svc.content.reject(UPLOADER, c.id, "السبب الأول")
    await env.svc.content.resubmit(STUDENT, c.id, PDF, TEX)
    await env.svc.content.reject(UPLOADER, c.id, "السبب الثاني")
    await env.click(STUDENT, St(a="rj", x=c.id))
    assert "السبب الثاني" in env.last_text(STUDENT) and "السبب الأول" not in env.last_text(STUDENT)
    with pytest.raises(DomainError):
        await _submit(env, 4)                               # rejected number stays occupied
    await env.svc.content.resubmit(STUDENT, c.id, PDF, TEX)
    approved = await env.svc.content.approve(UPLOADER, c.id)
    assert approved.id == c.id and approved.status == "approved"
    async with env.svc.db.read() as conn:
        assert await repo._scalar(conn, "SELECT COUNT(*) FROM contents") == 1   # same record, no history rows
    assert len(env.tg.documents_in(CH.approved_pdf)) == 1 and env.tg.documents_in(CH.temp_pdf) == []


# ═════════════ 6. deletion with retries ═════════════
async def test_deletion_full_cleanup_with_retry(seeded):
    env = seeded
    c = await _submit(env, 1)
    await env.svc.content.approve(UPLOADER, c.id)
    await env.svc.content.send_preview(ADMIN, c.id)
    env.tg.fail_when(lambda m: type(m).__name__ == "DeleteMessage" and m.chat_id == CH.approved_tex)
    report = await env.svc.content.delete(ADMIN, c.id)
    assert not report.complete and report.pending + report.failed >= 1
    with pytest.raises(DomainError):
        await env.svc.content.get(c.id)                     # record gone, file reference kept in the queue
    async with env.svc.db.read() as conn:
        refs = await repo._all(conn, "SELECT chat_id FROM cleanup_queue WHERE status IN ('pending','failed')")
    assert [r[0] for r in refs] == [CH.approved_tex]
    env.tg.clear_failures()
    async with env.svc.db.tx() as conn:
        await conn.execute("UPDATE cleanup_queue SET next_attempt_at = '2000-01-01' WHERE status = 'pending'")
    await env.svc.cleanup.process_due()
    assert env.tg.documents_in(CH.approved_tex) == [] and env.tg.documents_in(ADMIN) == []
    await _open_picker(env)
    assert env.picker(STUDENT)[1] == ("1", "nb")            # number freed


# ═════════════ migration ═════════════
def _build_v1(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(FIXTURE_V1.read_text(encoding="utf-8"))
    now = "2026-01-01T00:00:00+00:00"
    con.executescript(f"""
        INSERT INTO users (telegram_id, full_name, role, created_at, updated_at) VALUES
            ({ADMIN}, 'admin', 'admin', '{now}', '{now}'), ({STUDENT}, 'طالب', 'student', '{now}', '{now}'),
            ({UPLOADER}, 'رافع', 'uploader', '{now}', '{now}');
        INSERT INTO specializations (id, year_id, name, created_at) VALUES (1, 4, 'برمجيات', '{now}');
        INSERT INTO subjects (id, year_id, specialization_id, name, code, created_at, updated_at) VALUES
            (1, 1, NULL, 'برمجة 1', 'CS101', '{now}', '{now}'), (2, 4, 1, 'هندسة برمجيات', 'SE401', '{now}', '{now}');
        INSERT INTO student_subjects (student_id, subject_id, assigned_at) VALUES ({STUDENT}, 1, '{now}'),
                                                                          ({STUDENT}, 2, '{now}');
        INSERT INTO contents (id, subject_id, content_type, number, student_id, status, submitted_at,
                              status_changed_at, created_at, decided_at, reviewer_id)
            VALUES (1, 1, 'lecture', 1, {STUDENT}, 'approved', '{now}', '{now}', '{now}', '{now}', {UPLOADER}),
                   (2, 2, 'session', 3, {STUDENT}, 'pending', '{now}', '{now}', '{now}', NULL, NULL);
        INSERT INTO content_files (content_id, kind, stage, chat_id, message_id, file_id, updated_at) VALUES
            (1, 'pdf', 'approved', {CH.approved_pdf}, 11, 'F1', '{now}'),
            (1, 'tex', 'approved', {CH.approved_tex}, 12, 'F2', '{now}'),
            (2, 'pdf', 'temp', {CH.temp_pdf}, 13, 'F3', '{now}'),
            (2, 'tex', 'temp', {CH.temp_tex}, 14, 'F4', '{now}');
        INSERT INTO settings (key, value, updated_by, updated_at) VALUES
            ('protect_forwarding', '1', {ADMIN}, '{now}'), ('protect_saving', '0', {ADMIN}, '{now}'),
            ('support_username', 'ITGenix_Support', {ADMIN}, '{now}');
        PRAGMA user_version = 1;
    """)
    con.commit()
    con.close()


async def test_migration_v1_to_v2_preserves_data(tmp_path):
    path = tmp_path / "bot.db"
    _build_v1(path)
    db = Database(str(path))
    await db.connect()
    try:
        assert Path(f"{path}.v1.bak").exists()                         # backup before altering
        async with db.read() as c:
            assert await repo._scalar(c, "PRAGMA user_version") == SCHEMA_VERSION
            subjects = {s.code: s for s in await repo.unconfirmed_subjects(c)}
            assert set(subjects) == {"CS101", "SE401"}
            assert all(s.semester == 1 and not s.semester_confirmed for s in subjects.values())
            assert subjects["SE401"].specialization_id == 1
            assert await repo._scalar(c, "SELECT COUNT(*) FROM contents") == 2
            assert await repo._scalar(c, "SELECT COUNT(*) FROM student_subjects") == 2
            files = await repo._all(c, "SELECT protect_requested, protected, message_id FROM content_files")
            assert len(files) == 4 and all(r[0] == 1 and r[1] is None for r in files)
            settings = dict(await repo._all(c, "SELECT key, value FROM settings"))
            assert settings == {"support_username": "ITGenix_Support"}     # no protection configuration left
            assert await repo.number_statuses(c, 2, "session") == {3: "pending"}
            with pytest.raises(sqlite3.IntegrityError):
                await c.execute("UPDATE subjects SET semester = 3 WHERE id = 1")
    finally:
        await db.close()

    db = Database(str(path))                                          # idempotent re-open
    await db.connect()
    await db.close()


async def test_migrated_database_runs_with_services(tmp_path):
    from bot.app import create_bot
    from bot.config import Config
    from bot.services.container import build_services
    from tests.fake_telegram import FakeTelegram

    path = tmp_path / "bot.db"
    _build_v1(path)
    config = Config(bot_token="42:TEST", admin_ids=frozenset({ADMIN}), channels=CH, database_path=str(path),
                    cleanup_max_attempts=3)
    db = Database(str(path))
    await db.connect()
    tg = FakeTelegram()
    for cid, mid, fid in ((CH.approved_pdf, 11, "F1"), (CH.approved_tex, 12, "F2"),
                          (CH.temp_pdf, 13, "F3"), (CH.temp_tex, 14, "F4")):
        tg.messages[(cid, mid)] = {"document": {"file_id": fid}}
    svc = build_services(config, db, create_bot(config, session=tg))
    try:
        stats = await svc.protection.stats()
        assert stats["unknown"] == 4 and stats["outdated"] == 2          # v1 protected temp posts for uploaders
        await svc.cleanup.tick()                                          # the worker applies the permanent rule
        async with db.read() as c:
            rows = {r[0]: (r[1], r[2]) for r in await repo._all(
                c, "SELECT chat_id, protect_requested, protected FROM content_files")}
        assert rows[CH.temp_pdf] == (0, 0) and rows[CH.temp_tex] == (0, 0)      # re-published unprotected
        assert rows[CH.approved_pdf] == (1, None)                              # already protected: untouched
        assert (CH.temp_pdf, 13) not in tg.messages                            # old post removed

        await svc.academic.update_subject(ADMIN, 2, "semester", 2)
        assert [s.code for s in await svc.academic.unconfirmed_subjects()] == ["CS101"]
        assert (await svc.academic.subject(2)).semester == 2
        c2 = await svc.content.approve(UPLOADER, 2)                            # existing workflow still works
        assert c2.status == "approved"
        counts = await svc.content.approved_counts()
        assert counts.year(4) == 1 and counts.semester(4, 1, 2) == 1
    finally:
        await db.close()
