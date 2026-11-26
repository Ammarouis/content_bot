"""Failure handling, rollback, concurrency, cleanup queue and constraint tests (service level)."""
from __future__ import annotations

import asyncio

import pytest
from aiogram.methods import DeleteMessage, SendDocument

from bot.db import repositories as repo
from bot.models import FileInfo
from bot.services.errors import DomainError
from tests.conftest import ADMIN, CH, STUDENT, STUDENT2, UPLOADER

PDF = FileInfo("PDF1", "UPDF1", "a.pdf", 100)
TEX = FileInfo("TEX1", "UTEX1", "a.tex", 100)


async def _submit(env, number=1, ctype="lecture"):
    return await env.svc.content.submit(STUDENT, env.subject_id, ctype, number, PDF, None, TEX)


async def _queue(env):
    async with env.svc.db.read() as c:
        return [dict(r) for r in await repo._all(c, "SELECT * FROM cleanup_queue ORDER BY id")]


async def test_submit_failure_rolls_back_and_frees_number(seeded):
    env = seeded
    env.tg.fail_when(lambda m: isinstance(m, SendDocument) and m.chat_id == CH.temp_tex)
    with pytest.raises(DomainError) as ei:
        await _submit(env)
    assert ei.value.code == "upload_failed"
    assert env.tg.in_chat(CH.temp_pdf) == []                    # already posted PDF was cleaned up
    async with env.svc.db.read() as c:
        assert not await repo.content_exists(c, env.subject_id, "lecture", 1)
    env.tg.clear_failures()
    content = await _submit(env)
    assert content.status == "pending"


async def test_approve_failure_rolls_back_to_pending(seeded):
    env = seeded
    content = await _submit(env)
    env.tg.fail_when(lambda m: isinstance(m, SendDocument) and m.chat_id == CH.approved_tex)
    with pytest.raises(DomainError) as ei:
        await env.svc.content.approve(UPLOADER, content.id)
    assert ei.value.code == "approve_failed"
    c = await env.svc.content.get(content.id)
    assert c.status == "pending" and all(f.stage == "temp" for f in c.files)
    assert env.tg.in_chat(CH.approved_pdf) == []               # partial copy removed
    assert len(env.tg.in_chat(CH.temp_pdf)) == 1               # temp files intact
    env.tg.clear_failures()
    c = await env.svc.content.approve(UPLOADER, content.id)
    assert c.status == "approved"


async def test_concurrent_approvals_only_one_wins(seeded):
    env = seeded
    content = await _submit(env)
    results = await asyncio.gather(env.svc.content.approve(UPLOADER, content.id),
                                   env.svc.content.approve(ADMIN, content.id),
                                   env.svc.content.reject(UPLOADER, content.id, "سبب الرفض"),
                                   return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception)]
    errors = [r for r in results if isinstance(r, DomainError)]
    assert len(ok) == 1 and len(errors) == 2
    assert all(e.code == "not_pending" for e in errors)
    assert len(env.tg.in_chat(CH.approved_pdf)) <= 1


async def test_concurrent_duplicate_submissions(seeded):
    env = seeded
    results = await asyncio.gather(*[_submit(env, number=5) for _ in range(3)], return_exceptions=True)
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert sum(isinstance(r, DomainError) and r.code == "duplicate_content" for r in results) == 2


async def test_delete_blocked_while_in_flight(seeded):
    env = seeded
    content = await _submit(env)
    async with env.svc.db.tx() as c:
        await repo.transition(c, content.id, "pending", "approving")
    with pytest.raises(DomainError) as ei:
        await env.svc.content.delete(ADMIN, content.id)
    assert ei.value.code == "content_busy"


async def test_partial_deletion_retries_and_notifies(seeded):
    env = seeded
    content = await _submit(env)
    content = await env.svc.content.approve(UPLOADER, content.id)
    rule = env.tg.fail_when(lambda m: isinstance(m, DeleteMessage) and m.chat_id == CH.approved_tex,
                            "Bad Request: message can't be deleted")
    report = await env.svc.content.delete(ADMIN, content.id)
    assert not report.complete and report.pending == 1 and report.done == 1
    async with env.svc.db.read() as c:
        assert not await repo.content_exists(c, env.subject_id, "lecture", 1)   # number freed immediately
    q = [r for r in await _queue(env) if r["job_id"] == report.job_id]
    assert any(r["status"] == "pending" and r["attempts"] == 1 and r["last_error"] for r in q)

    # retries until max attempts → failed (still tracked), admin can retry later
    for _ in range(3):
        async with env.svc.db.tx() as c:
            await c.execute("UPDATE cleanup_queue SET next_attempt_at = '2000-01-01 00:00:00' WHERE status='pending'")
        await env.svc.cleanup.tick()
    q = [r for r in await _queue(env) if r["job_id"] == report.job_id]
    assert any(r["status"] == "failed" for r in q)
    assert "تحتاج إلى تدخل" in env.last_text(ADMIN)
    assert len(env.tg.in_chat(CH.approved_tex)) == 1          # reference not lost, message still exists

    env.tg.failures.remove(rule)
    n = await env.svc.cleanup.retry_failed(ADMIN)
    assert n == 1
    assert env.tg.in_chat(CH.approved_tex) == []
    async with env.svc.db.read() as c:
        job = await repo.get_job(c, report.job_id)
    assert job["status"] == "completed"
    assert "اكتمل الحذف بالكامل" in env.last_text(ADMIN)


async def test_already_deleted_message_counts_as_done(seeded):
    env = seeded
    content = await _submit(env)
    f = content.file("pdf")
    del env.tg.messages[(f.chat_id, f.message_id)]          # someone removed it manually
    report = await env.svc.content.delete(ADMIN, content.id)
    assert report.complete


async def test_crash_recovery_rolls_back_transitional_states(seeded):
    env = seeded
    pending = await _submit(env, number=1)
    rejected = await _submit(env, number=2)
    await env.svc.content.reject(UPLOADER, rejected.id, "سبب الرفض")
    # simulate crashes mid-operation: claimed states + posted ("held") messages
    stray = (await env.svc.gateway.send_document(CH.approved_pdf, "X", "c", False)).message_id
    stray2 = (await env.svc.gateway.send_document(CH.temp_pdf, "Y", "c", False)).message_id
    async with env.svc.db.tx() as c:
        await repo.transition(c, pending.id, "pending", "approving")
        await repo.enqueue(c, CH.approved_pdf, stray, "approve", content_ref=pending.id, status="held")
        await repo.transition(c, rejected.id, "rejected", "resubmitting")
        await repo.enqueue(c, CH.temp_pdf, stray2, "resubmit", content_ref=rejected.id, status="held")
        cid = await repo.insert_content(c, env.subject_id, "lecture", 3, STUDENT, "reason text")
    rolled = await env.svc.cleanup.recover(stale_only=False)
    assert rolled == 3
    assert (await env.svc.content.get(pending.id)).status == "pending"
    assert (await env.svc.content.get(rejected.id)).status == "rejected"
    with pytest.raises(DomainError):
        await env.svc.content.get(cid)                          # interrupted upload removed, number freed
    await env.svc.cleanup.process_due()
    assert (CH.approved_pdf, stray) not in env.tg.messages and (CH.temp_pdf, stray2) not in env.tg.messages


async def test_preview_expiry(seeded):
    env = seeded
    content = await _submit(env)
    sent, failed = await env.svc.content.send_preview(UPLOADER, content.id)
    assert (sent, failed) == (2, 0)
    async with env.svc.db.tx() as c:
        await c.execute("UPDATE preview_messages SET created_at = '2000-01-01 00:00:00'")
    await env.svc.cleanup.tick()
    assert not [k for k in env.tg.in_chat(UPLOADER) if "copied_from" in env.tg.messages[k]]
    async with env.svc.db.read() as c:
        assert await repo.previews_for(c, content.id) == []


async def test_service_level_rbac(seeded):
    env = seeded
    content = await _submit(env)
    for coro in (env.svc.content.approve(STUDENT, content.id),
                 env.svc.content.reject(STUDENT2, content.id, "سبب"),
                 env.svc.content.delete(UPLOADER, content.id),
                 env.svc.users.add(UPLOADER, 555555, "اسم", "admin"),
                 env.svc.content.submit(UPLOADER, env.subject_id, "lecture", 9, PDF, None, TEX),
                 env.svc.content.submit(STUDENT2, env.subject_id, "lecture", 9, PDF, None, TEX),
                 env.svc.content.resubmit(STUDENT2, content.id, PDF, TEX)):
        with pytest.raises(DomainError):
            await coro


async def test_academic_constraints(seeded):
    env = seeded
    a = env.svc.academic
    with pytest.raises(DomainError) as ei:
        await a.create_subject(ADMIN, 4, None, 1, "مادة", "AB12")
    assert ei.value.code == "specialization_required"
    with pytest.raises(DomainError) as ei:
        await a.add_specialization(ADMIN, 2, "اختصاص")
    assert ei.value.code == "year_has_no_specializations"
    spec4 = await a.add_specialization(ADMIN, 4, "شبكات")
    spec5 = await a.add_specialization(ADMIN, 5, "شبكات")
    with pytest.raises(DomainError) as ei:
        await a.create_subject(ADMIN, 1, spec4, 1, "مادة", "AB12")
    assert ei.value.code == "specialization_not_allowed"
    with pytest.raises(DomainError) as ei:
        await a.create_subject(ADMIN, 4, spec5, 1, "مادة", "AB12")
    assert ei.value.code == "specialization_year_mismatch"
    with pytest.raises(DomainError) as ei:
        await a.create_subject(ADMIN, 1, None, 1, "مادة", "CS101")
    assert ei.value.code == "subject_code_exists"
    for bad in ("1AB", "A", "AB-1", "عربي", "A" * 21):
        with pytest.raises(DomainError):
            await a.create_subject(ADMIN, 1, None, 1, "مادة", bad)
    sid = await a.create_subject(ADMIN, 4, spec4, 1, "شبكات 1", "net401")
    with pytest.raises(DomainError) as ei:
        await a.delete_specialization(ADMIN, spec4)
    assert ei.value.code == "specialization_has_subjects"
    await _submit(env)
    with pytest.raises(DomainError) as ei:
        await a.delete_subject(ADMIN, env.subject_id)
    assert ei.value.code == "subject_has_content"
    await a.delete_subject(ADMIN, sid)
    await a.delete_specialization(ADMIN, spec4)


async def test_removed_student_keeps_content(seeded):
    env = seeded
    content = await _submit(env)
    await env.svc.users.remove(ADMIN, STUDENT)
    c = await env.svc.content.get(content.id)
    assert c.student_id is None and c.status == "pending"
