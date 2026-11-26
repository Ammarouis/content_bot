"""All SQL lives here. Functions receive an open connection (inside Database.tx / Database.read)."""
from __future__ import annotations

from typing import Iterable, Sequence

import aiosqlite

from bot.db.database import utc_offset, utcnow
from bot.models import (
    AppUser, Content, ContentFile, QueueItem, Specialization, Subject, Year,
)

Conn = aiosqlite.Connection


async def _one(conn: Conn, sql: str, params: Sequence = ()) -> aiosqlite.Row | None:
    async with conn.execute(sql, params) as cur:
        return await cur.fetchone()


async def _all(conn: Conn, sql: str, params: Sequence = ()) -> list[aiosqlite.Row]:
    async with conn.execute(sql, params) as cur:
        return list(await cur.fetchall())


async def _scalar(conn: Conn, sql: str, params: Sequence = ()):
    row = await _one(conn, sql, params)
    return row[0] if row else None


# ───────────────────────────── users ─────────────────────────────

def _user(r: aiosqlite.Row) -> AppUser:
    return AppUser(r["telegram_id"], r["full_name"], r["role"], r["created_at"])


async def get_user(conn: Conn, telegram_id: int) -> AppUser | None:
    r = await _one(conn, "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    return _user(r) if r else None


async def insert_user(conn: Conn, telegram_id: int, full_name: str, role: str, added_by: int | None) -> None:
    now = utcnow()
    await conn.execute(
        "INSERT INTO users (telegram_id, full_name, role, added_by, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (telegram_id, full_name, role, added_by, now, now),
    )


async def upsert_bootstrap_admin(conn: Conn, telegram_id: int) -> None:
    now = utcnow()
    await conn.execute(
        """INSERT INTO users (telegram_id, full_name, role, added_by, created_at, updated_at)
           VALUES (?, 'مدير النظام', 'admin', NULL, ?, ?)
           ON CONFLICT(telegram_id) DO UPDATE SET role = 'admin', updated_at = excluded.updated_at
           WHERE users.role <> 'admin'""",
        (telegram_id, now, now),
    )


async def update_user_role(conn: Conn, telegram_id: int, role: str) -> int:
    cur = await conn.execute("UPDATE users SET role = ?, updated_at = ? WHERE telegram_id = ?",
                             (role, utcnow(), telegram_id))
    return cur.rowcount


async def update_user_name(conn: Conn, telegram_id: int, name: str) -> int:
    cur = await conn.execute("UPDATE users SET full_name = ?, updated_at = ? WHERE telegram_id = ?",
                             (name, utcnow(), telegram_id))
    return cur.rowcount


async def delete_user(conn: Conn, telegram_id: int) -> int:
    cur = await conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
    return cur.rowcount


async def list_users(conn: Conn, role: str | None, limit: int, offset: int) -> tuple[list[AppUser], int]:
    where, params = ("WHERE role = ?", [role]) if role else ("", [])
    total = await _scalar(conn, f"SELECT COUNT(*) FROM users {where}", params)
    rows = await _all(conn, f"SELECT * FROM users {where} ORDER BY role, full_name LIMIT ? OFFSET ?",
                      [*params, limit, offset])
    return [_user(r) for r in rows], total


async def user_ids_by_role(conn: Conn, role: str) -> list[int]:
    return [r[0] for r in await _all(conn, "SELECT telegram_id FROM users WHERE role = ?", (role,))]


async def clear_student_subjects(conn: Conn, student_id: int) -> None:
    await conn.execute("DELETE FROM student_subjects WHERE student_id = ?", (student_id,))


# ───────────────────────────── academic ─────────────────────────────

async def list_years(conn: Conn) -> list[Year]:
    rows = await _all(conn, "SELECT * FROM academic_years ORDER BY id")
    return [Year(r["id"], r["name"], bool(r["requires_specialization"])) for r in rows]


async def get_year(conn: Conn, year_id: int) -> Year | None:
    r = await _one(conn, "SELECT * FROM academic_years WHERE id = ?", (year_id,))
    return Year(r["id"], r["name"], bool(r["requires_specialization"])) if r else None


async def list_specializations(conn: Conn, year_id: int) -> list[Specialization]:
    rows = await _all(conn, "SELECT * FROM specializations WHERE year_id = ? ORDER BY name", (year_id,))
    return [Specialization(r["id"], r["year_id"], r["name"]) for r in rows]


async def get_specialization(conn: Conn, spec_id: int) -> Specialization | None:
    r = await _one(conn, "SELECT * FROM specializations WHERE id = ?", (spec_id,))
    return Specialization(r["id"], r["year_id"], r["name"]) if r else None


async def insert_specialization(conn: Conn, year_id: int, name: str) -> int:
    cur = await conn.execute("INSERT INTO specializations (year_id, name, created_at) VALUES (?,?,?)",
                             (year_id, name, utcnow()))
    return cur.lastrowid


async def rename_specialization(conn: Conn, spec_id: int, name: str) -> int:
    cur = await conn.execute("UPDATE specializations SET name = ? WHERE id = ?", (name, spec_id))
    return cur.rowcount


async def delete_specialization(conn: Conn, spec_id: int) -> int:
    cur = await conn.execute("DELETE FROM specializations WHERE id = ?", (spec_id,))
    return cur.rowcount


async def count_subjects_in_spec(conn: Conn, spec_id: int) -> int:
    return await _scalar(conn, "SELECT COUNT(*) FROM subjects WHERE specialization_id = ?", (spec_id,))


_SUBJECT_SELECT = """
SELECT s.id, s.code, s.name, s.year_id, y.name AS year_name, s.specialization_id, sp.name AS spec_name,
       s.semester, s.semester_confirmed
FROM subjects s
JOIN academic_years y ON y.id = s.year_id
LEFT JOIN specializations sp ON sp.id = s.specialization_id
"""


def _subject(r: aiosqlite.Row) -> Subject:
    return Subject(r["id"], r["code"], r["name"], r["year_id"], r["year_name"],
                   r["specialization_id"], r["spec_name"], r["semester"], bool(r["semester_confirmed"]))


async def get_subject(conn: Conn, subject_id: int) -> Subject | None:
    r = await _one(conn, _SUBJECT_SELECT + " WHERE s.id = ?", (subject_id,))
    return _subject(r) if r else None


async def get_subject_by_code(conn: Conn, code: str) -> Subject | None:
    r = await _one(conn, _SUBJECT_SELECT + " WHERE s.code = ?", (code,))
    return _subject(r) if r else None


async def list_subjects(conn: Conn, year_id: int, spec_id: int | None, semester: int | None = None) -> list[Subject]:
    where, params = ["s.year_id = ?"], [year_id]
    if spec_id is None:
        where.append("s.specialization_id IS NULL")
    else:
        where.append("s.specialization_id = ?")
        params.append(spec_id)
    if semester is not None:
        where.append("s.semester = ?")
        params.append(semester)
    rows = await _all(conn, _SUBJECT_SELECT + " WHERE " + " AND ".join(where) + " ORDER BY s.semester, s.code", params)
    return [_subject(r) for r in rows]


async def unconfirmed_subjects(conn: Conn) -> list[Subject]:
    rows = await _all(conn, _SUBJECT_SELECT + " WHERE s.semester_confirmed = 0 ORDER BY s.year_id, s.code")
    return [_subject(r) for r in rows]


async def insert_subject(conn: Conn, code: str, name: str, year_id: int, spec_id: int | None, semester: int) -> int:
    now = utcnow()
    cur = await conn.execute(
        "INSERT INTO subjects (code, name, year_id, specialization_id, semester, semester_confirmed, created_at, "
        "updated_at) VALUES (?,?,?,?,?,1,?,?)", (code, name, year_id, spec_id, semester, now, now))
    return cur.lastrowid


async def update_subject_field(conn: Conn, subject_id: int, field: str, value: str | int) -> int:
    if field not in {"name", "code", "semester"}:
        raise ValueError(field)
    extra = ", semester_confirmed = 1" if field == "semester" else ""
    cur = await conn.execute(f"UPDATE subjects SET {field} = ?{extra}, updated_at = ? WHERE id = ?",
                             (value, utcnow(), subject_id))
    return cur.rowcount


async def delete_subject(conn: Conn, subject_id: int) -> int:
    cur = await conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    return cur.rowcount


async def subject_stats(conn: Conn, subject_id: int) -> dict:
    r = await _one(conn, """SELECT
            (SELECT COUNT(*) FROM contents WHERE subject_id = ?) AS contents,
            (SELECT COUNT(*) FROM student_subjects WHERE subject_id = ?) AS students""",
                   (subject_id, subject_id))
    return {"contents": r["contents"], "students": r["students"]}


async def student_subjects(conn: Conn, student_id: int) -> list[Subject]:
    rows = await _all(conn, _SUBJECT_SELECT + """
        JOIN student_subjects ss ON ss.subject_id = s.id
        WHERE ss.student_id = ? ORDER BY s.year_id, s.code""", (student_id,))
    return [_subject(r) for r in rows]


async def student_subject_ids(conn: Conn, student_id: int) -> set[int]:
    rows = await _all(conn, "SELECT subject_id FROM student_subjects WHERE student_id = ?", (student_id,))
    return {r[0] for r in rows}


async def is_assigned(conn: Conn, student_id: int, subject_id: int) -> bool:
    return bool(await _scalar(conn, "SELECT 1 FROM student_subjects WHERE student_id = ? AND subject_id = ?",
                              (student_id, subject_id)))


async def assign_subject(conn: Conn, student_id: int, subject_id: int) -> None:
    await conn.execute("INSERT OR IGNORE INTO student_subjects (student_id, subject_id, assigned_at) VALUES (?,?,?)",
                       (student_id, subject_id, utcnow()))


async def unassign_subject(conn: Conn, student_id: int, subject_id: int) -> None:
    await conn.execute("DELETE FROM student_subjects WHERE student_id = ? AND subject_id = ?",
                       (student_id, subject_id))


# ───────────────────────────── contents ─────────────────────────────

_CONTENT_SELECT = """
SELECT c.*, s.code AS subject_code, s.name AS subject_name, y.name AS year_name, sp.name AS spec_name,
       s.semester AS semester, st.full_name AS student_name, rv.full_name AS reviewer_name
FROM contents c
JOIN subjects s ON s.id = c.subject_id
JOIN academic_years y ON y.id = s.year_id
LEFT JOIN specializations sp ON sp.id = s.specialization_id
LEFT JOIN users st ON st.telegram_id = c.student_id
LEFT JOIN users rv ON rv.telegram_id = c.reviewer_id
"""


def _content(r: aiosqlite.Row, files: Iterable[ContentFile] = ()) -> Content:
    return Content(
        id=r["id"], subject_id=r["subject_id"], subject_code=r["subject_code"], subject_name=r["subject_name"],
        year_name=r["year_name"], specialization_name=r["spec_name"], content_type=r["content_type"],
        number=r["number"], student_id=r["student_id"], student_name=r["student_name"], status=r["status"],
        pdf_skip_reason=r["pdf_skip_reason"], rejection_reason=r["rejection_reason"],
        reviewer_id=r["reviewer_id"], reviewer_name=r["reviewer_name"], submitted_at=r["submitted_at"],
        decided_at=r["decided_at"], files=tuple(files), semester=r["semester"])


def _file(r: aiosqlite.Row) -> ContentFile:
    return ContentFile(r["content_id"], r["kind"], r["stage"], r["chat_id"], r["message_id"],
                       r["file_id"], r["file_name"], r["file_size"], bool(r["protect_requested"]),
                       None if r["protected"] is None else bool(r["protected"]))


async def get_files(conn: Conn, content_id: int) -> list[ContentFile]:
    rows = await _all(conn, "SELECT * FROM content_files WHERE content_id = ? ORDER BY kind", (content_id,))
    return [_file(r) for r in rows]


async def get_content(conn: Conn, content_id: int) -> Content | None:
    r = await _one(conn, _CONTENT_SELECT + " WHERE c.id = ?", (content_id,))
    if not r:
        return None
    return _content(r, await get_files(conn, content_id))


async def find_content(conn: Conn, subject_id: int, ctype: str, number: int) -> Content | None:
    r = await _one(conn, _CONTENT_SELECT + " WHERE c.subject_id = ? AND c.content_type = ? AND c.number = ?",
                   (subject_id, ctype, number))
    return _content(r) if r else None


async def content_exists(conn: Conn, subject_id: int, ctype: str, number: int) -> bool:
    return bool(await _scalar(conn,
                              "SELECT 1 FROM contents WHERE subject_id = ? AND content_type = ? AND number = ?",
                              (subject_id, ctype, number)))


async def insert_content(conn: Conn, subject_id: int, ctype: str, number: int, student_id: int,
                         pdf_skip_reason: str | None) -> int:
    now = utcnow()
    cur = await conn.execute(
        """INSERT INTO contents (subject_id, content_type, number, student_id, status, pdf_skip_reason,
                                 submitted_at, status_changed_at, created_at)
           VALUES (?,?,?,?, 'uploading', ?, ?, ?, ?)""",
        (subject_id, ctype, number, student_id, pdf_skip_reason, now, now, now))
    return cur.lastrowid


async def transition(conn: Conn, content_id: int, expected: str | Sequence[str], new: str, **fields) -> int:
    """Conditional status change: succeeds only if the current status is one of ``expected``."""
    expected = (expected,) if isinstance(expected, str) else tuple(expected)
    allowed = {"rejection_reason", "reviewer_id", "decided_at", "pdf_skip_reason", "submitted_at"}
    sets, params = ["status = ?", "status_changed_at = ?"], [new, utcnow()]
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(k)
        sets.append(f"{k} = ?")
        params.append(v)
    marks = ",".join("?" * len(expected))
    cur = await conn.execute(f"UPDATE contents SET {', '.join(sets)} WHERE id = ? AND status IN ({marks})",
                             (*params, content_id, *expected))
    return cur.rowcount


async def get_status(conn: Conn, content_id: int) -> str | None:
    return await _scalar(conn, "SELECT status FROM contents WHERE id = ?", (content_id,))


async def delete_content_row(conn: Conn, content_id: int) -> int:
    cur = await conn.execute("DELETE FROM contents WHERE id = ?", (content_id,))
    return cur.rowcount


async def upsert_file(conn: Conn, content_id: int, kind: str, stage: str, chat_id: int, message_id: int,
                      file_id: str, file_unique_id: str | None, file_name: str | None, file_size: int | None,
                      protect_requested: bool, protected: bool) -> None:
    await conn.execute(
        """INSERT INTO content_files (content_id, kind, stage, chat_id, message_id, file_id, file_unique_id,
                                      file_name, file_size, updated_at, protect_requested, protected)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(content_id, kind) DO UPDATE SET
             stage = excluded.stage, chat_id = excluded.chat_id, message_id = excluded.message_id,
             file_id = excluded.file_id, file_unique_id = excluded.file_unique_id,
             file_name = excluded.file_name, file_size = excluded.file_size, updated_at = excluded.updated_at,
             protect_requested = excluded.protect_requested, protected = excluded.protected""",
        (content_id, kind, stage, chat_id, message_id, file_id, file_unique_id, file_name, file_size, utcnow(),
         int(protect_requested), int(protected)))


async def move_file(conn: Conn, content_id: int, kind: str, stage: str, chat_id: int, message_id: int,
                    protect_requested: bool, protected: bool) -> None:
    await conn.execute(
        "UPDATE content_files SET stage = ?, chat_id = ?, message_id = ?, protect_requested = ?, protected = ?, "
        "updated_at = ? WHERE content_id = ? AND kind = ?",
        (stage, chat_id, message_id, int(protect_requested), int(protected), utcnow(), content_id, kind))


async def get_file(conn: Conn, content_id: int, kind: str) -> ContentFile | None:
    r = await _one(conn, "SELECT * FROM content_files WHERE content_id = ? AND kind = ?", (content_id, kind))
    return _file(r) if r else None


_PROTECTION_TARGET = """
FROM content_files cf JOIN contents c ON c.id = cf.content_id JOIN subjects s ON s.id = c.subject_id
WHERE c.status IN ('pending', 'approved', 'rejected')
  AND ((cf.stage = 'temp' AND cf.protect_requested <> ?) OR (cf.stage = 'approved' AND cf.protect_requested <> ?))
"""


async def files_needing_protection_sync(conn: Conn, temp_flag: bool, approved_flag: bool,
                                        limit: int) -> list[ContentFile]:
    rows = await _all(conn, "SELECT cf.* " + _PROTECTION_TARGET +
                      " ORDER BY cf.stage, s.code, c.content_type, c.number, cf.kind LIMIT ?",
                      (int(temp_flag), int(approved_flag), limit))
    return [_file(r) for r in rows]


async def protection_stats(conn: Conn, temp_flag: bool, approved_flag: bool) -> dict:
    total = await _scalar(conn, "SELECT COUNT(*) FROM content_files")
    outdated = await _scalar(conn, "SELECT COUNT(*) " + _PROTECTION_TARGET, (int(temp_flag), int(approved_flag)))
    r = await _one(conn, """SELECT
        SUM(CASE WHEN protected = 1 THEN 1 ELSE 0 END) AS verified_protected,
        SUM(CASE WHEN protected = 0 THEN 1 ELSE 0 END) AS verified_open,
        SUM(CASE WHEN protected IS NULL THEN 1 ELSE 0 END) AS unknown,
        SUM(CASE WHEN protect_requested = 1 AND protected = 0 THEN 1 ELSE 0 END) AS not_honoured
        FROM content_files""")
    return {"total": total, "outdated": outdated, "verified_protected": r["verified_protected"] or 0,
            "verified_open": r["verified_open"] or 0, "unknown": r["unknown"] or 0,
            "not_honoured": r["not_honoured"] or 0}


async def replace_file_message(conn: Conn, content_id: int, kind: str, message_id: int, protect_requested: bool,
                               protected: bool) -> None:
    await conn.execute("UPDATE content_files SET message_id = ?, protect_requested = ?, protected = ?, updated_at = ? "
                       "WHERE content_id = ? AND kind = ?",
                       (message_id, int(protect_requested), int(protected), utcnow(), content_id, kind))


async def delete_file_row(conn: Conn, content_id: int, kind: str) -> None:
    await conn.execute("DELETE FROM content_files WHERE content_id = ? AND kind = ?", (content_id, kind))


async def list_contents(conn: Conn, *, status: str | Sequence[str] | None = None, subject_id: int | None = None,
                        student_id: int | None = None, ctype: str | None = None, number: int | None = None,
                        order: str = "c.submitted_at ASC", limit: int = 10, offset: int = 0
                        ) -> tuple[list[Content], int]:
    where, params = [], []
    if status is not None:
        statuses = (status,) if isinstance(status, str) else tuple(status)
        where.append(f"c.status IN ({','.join('?' * len(statuses))})")
        params.extend(statuses)
    for col, val in (("c.subject_id", subject_id), ("c.student_id", student_id),
                     ("c.content_type", ctype), ("c.number", number)):
        if val is not None:
            where.append(f"{col} = ?")
            params.append(val)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    if order not in {"c.submitted_at ASC", "c.submitted_at DESC", "c.content_type, c.number",
                     "c.status_changed_at DESC"}:
        raise ValueError(order)
    total = await _scalar(conn, f"SELECT COUNT(*) FROM contents c {clause}", params)
    rows = await _all(conn, f"{_CONTENT_SELECT} {clause} ORDER BY {order}, c.id LIMIT ? OFFSET ?",
                      [*params, limit, offset])
    return [_content(r) for r in rows], total


async def approved_counts(conn: Conn) -> list[aiosqlite.Row]:
    """Approved content counts per subject and type, with each subject's place in the hierarchy."""
    return await _all(conn, """SELECT s.id AS subject_id, s.year_id, s.specialization_id, s.semester,
                                      c.content_type, COUNT(*) AS n
                               FROM contents c JOIN subjects s ON s.id = c.subject_id
                               WHERE c.status = 'approved'
                               GROUP BY s.id, c.content_type""")


async def number_statuses(conn: Conn, subject_id: int, ctype: str) -> dict[int, str]:
    rows = await _all(conn, "SELECT number, status FROM contents WHERE subject_id = ? AND content_type = ?",
                      (subject_id, ctype))
    return {r[0]: r[1] for r in rows}


async def subject_number_summary(conn: Conn, subject_id: int) -> list[aiosqlite.Row]:
    return await _all(conn, """SELECT content_type, status, number FROM contents
                               WHERE subject_id = ? ORDER BY content_type, number""", (subject_id,))


async def transitional_contents(conn: Conn, older_than: str | None) -> list[aiosqlite.Row]:
    sql = "SELECT id, status, student_id FROM contents WHERE status IN ('uploading','approving','resubmitting')"
    params: list = []
    if older_than:
        sql += " AND status_changed_at < ?"
        params.append(older_than)
    return await _all(conn, sql, params)


# ───────────────────────────── preview messages ─────────────────────────────

async def add_preview(conn: Conn, content_id: int, chat_id: int, message_id: int) -> None:
    await conn.execute("INSERT OR IGNORE INTO preview_messages (content_id, chat_id, message_id, created_at) "
                       "VALUES (?,?,?,?)", (content_id, chat_id, message_id, utcnow()))


async def previews_for(conn: Conn, content_id: int) -> list[tuple[int, int]]:
    rows = await _all(conn, "SELECT chat_id, message_id FROM preview_messages WHERE content_id = ?", (content_id,))
    return [(r[0], r[1]) for r in rows]


async def delete_previews_for(conn: Conn, content_id: int) -> None:
    await conn.execute("DELETE FROM preview_messages WHERE content_id = ?", (content_id,))


async def expired_previews(conn: Conn, older_than: str, limit: int = 500) -> list[aiosqlite.Row]:
    return await _all(conn, "SELECT id, content_id, chat_id, message_id FROM preview_messages "
                            "WHERE created_at < ? ORDER BY id LIMIT ?", (older_than, limit))


async def delete_preview_ids(conn: Conn, ids: Sequence[int]) -> None:
    if ids:
        await conn.execute(f"DELETE FROM preview_messages WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))


# ───────────────────────────── cleanup queue ─────────────────────────────

async def enqueue(conn: Conn, chat_id: int, message_id: int, reason: str, *, content_ref: int | None = None,
                  job_id: int | None = None, status: str = "pending") -> None:
    """Add a message to the cleanup queue (idempotent). A 'done' entry is never resurrected."""
    now = utcnow()
    await conn.execute(
        """INSERT INTO cleanup_queue (chat_id, message_id, reason, content_ref, job_id, status, attempts,
                                      next_attempt_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,0,?,?,?)
           ON CONFLICT(chat_id, message_id) DO UPDATE SET
             status = CASE WHEN cleanup_queue.status = 'done' THEN 'done' ELSE excluded.status END,
             reason = excluded.reason,
             job_id = COALESCE(excluded.job_id, cleanup_queue.job_id),
             content_ref = COALESCE(excluded.content_ref, cleanup_queue.content_ref),
             next_attempt_at = excluded.next_attempt_at,
             updated_at = excluded.updated_at""",
        (chat_id, message_id, reason, content_ref, job_id, status, now, now, now))


async def release_holds(conn: Conn, content_id: int) -> None:
    await conn.execute("DELETE FROM cleanup_queue WHERE content_ref = ? AND status = 'held'", (content_id,))


async def activate_holds(conn: Conn, content_id: int, reason: str) -> int:
    cur = await conn.execute(
        "UPDATE cleanup_queue SET status = 'pending', reason = ?, next_attempt_at = ?, updated_at = ? "
        "WHERE content_ref = ? AND status = 'held'", (reason, utcnow(), utcnow(), content_id))
    return cur.rowcount


async def release_hold(conn: Conn, chat_id: int, message_id: int) -> None:
    await conn.execute("DELETE FROM cleanup_queue WHERE chat_id = ? AND message_id = ? AND status = 'held'",
                       (chat_id, message_id))


async def activate_hold(conn: Conn, chat_id: int, message_id: int, reason: str) -> None:
    await conn.execute("UPDATE cleanup_queue SET status = 'pending', reason = ?, next_attempt_at = ?, updated_at = ? "
                       "WHERE chat_id = ? AND message_id = ? AND status = 'held'",
                       (reason, utcnow(), utcnow(), chat_id, message_id))


async def activate_orphan_holds(conn: Conn, older_than: str) -> int:
    cur = await conn.execute(
        """UPDATE cleanup_queue SET status = 'pending', reason = 'orphan_hold', next_attempt_at = ?, updated_at = ?
           WHERE status = 'held' AND created_at < ?
             AND (content_ref IS NULL OR content_ref NOT IN
                  (SELECT id FROM contents WHERE status IN ('uploading','approving','resubmitting')))""",
        (utcnow(), utcnow(), older_than))
    return cur.rowcount


async def attach_open_items_to_job(conn: Conn, content_id: int, job_id: int) -> None:
    await conn.execute("UPDATE cleanup_queue SET job_id = ?, updated_at = ? "
                       "WHERE content_ref = ? AND status IN ('pending','failed','held')",
                       (job_id, utcnow(), content_id))
    await conn.execute("UPDATE cleanup_queue SET status = 'pending', attempts = 0, next_attempt_at = ? "
                       "WHERE job_id = ? AND status IN ('failed','held')", (utcnow(), job_id))


def _qi(r: aiosqlite.Row) -> QueueItem:
    return QueueItem(r["id"], r["chat_id"], r["message_id"], r["reason"], r["job_id"], r["attempts"])


async def due_items(conn: Conn, limit: int) -> list[QueueItem]:
    rows = await _all(conn, "SELECT * FROM cleanup_queue WHERE status = 'pending' AND next_attempt_at <= ? "
                            "ORDER BY next_attempt_at, id LIMIT ?", (utcnow(), limit))
    return [_qi(r) for r in rows]


async def job_open_items(conn: Conn, job_id: int) -> list[QueueItem]:
    rows = await _all(conn, "SELECT * FROM cleanup_queue WHERE job_id = ? AND status = 'pending' ORDER BY id",
                      (job_id,))
    return [_qi(r) for r in rows]


async def mark_item_done(conn: Conn, item_id: int, note: str | None = None) -> None:
    await conn.execute("UPDATE cleanup_queue SET status = 'done', attempts = attempts + 1, last_error = ?, "
                       "updated_at = ? WHERE id = ?", (note, utcnow(), item_id))


async def mark_item_retry(conn: Conn, item_id: int, error: str, max_attempts: int) -> None:
    row = await _one(conn, "SELECT attempts FROM cleanup_queue WHERE id = ?", (item_id,))
    if not row:
        return
    attempts = row[0] + 1
    if attempts >= max_attempts:
        await conn.execute("UPDATE cleanup_queue SET status = 'failed', attempts = ?, last_error = ?, updated_at = ? "
                           "WHERE id = ?", (attempts, error[:500], utcnow(), item_id))
    else:
        delay = min(30 * (2 ** (attempts - 1)), 3600)
        await conn.execute("UPDATE cleanup_queue SET attempts = ?, last_error = ?, next_attempt_at = ?, updated_at = ? "
                           "WHERE id = ?", (attempts, error[:500], utc_offset(seconds=delay), utcnow(), item_id))


async def queue_stats(conn: Conn) -> dict:
    rows = await _all(conn, "SELECT status, COUNT(*) FROM cleanup_queue GROUP BY status")
    stats = {"held": 0, "pending": 0, "done": 0, "failed": 0}
    stats.update({r[0]: r[1] for r in rows})
    jobs = await _all(conn, "SELECT status, COUNT(*) FROM deletion_jobs WHERE status <> 'completed' GROUP BY status")
    stats.update({f"jobs_{r[0]}": r[1] for r in jobs})
    return stats


async def failed_items(conn: Conn, limit: int = 10) -> list[aiosqlite.Row]:
    return await _all(conn, "SELECT * FROM cleanup_queue WHERE status = 'failed' ORDER BY id LIMIT ?", (limit,))


async def retry_failed(conn: Conn) -> int:
    cur = await conn.execute("UPDATE cleanup_queue SET status = 'pending', attempts = 0, next_attempt_at = ?, "
                             "updated_at = ? WHERE status = 'failed'", (utcnow(), utcnow()))
    await conn.execute("UPDATE deletion_jobs SET status = 'in_progress' WHERE status = 'needs_attention'")
    return cur.rowcount


async def purge_done(conn: Conn, older_than: str) -> None:
    await conn.execute("DELETE FROM cleanup_queue WHERE status = 'done' AND updated_at < ?", (older_than,))


async def create_job(conn: Conn, description: str, requested_by: int) -> int:
    cur = await conn.execute("INSERT INTO deletion_jobs (description, requested_by, status, created_at) "
                             "VALUES (?,?, 'in_progress', ?)", (description, requested_by, utcnow()))
    return cur.lastrowid


async def job_counts(conn: Conn, job_id: int) -> dict:
    rows = await _all(conn, "SELECT status, COUNT(*) FROM cleanup_queue WHERE job_id = ? GROUP BY status", (job_id,))
    counts = {"held": 0, "pending": 0, "done": 0, "failed": 0}
    counts.update({r[0]: r[1] for r in rows})
    return counts


async def open_jobs(conn: Conn) -> list[aiosqlite.Row]:
    return await _all(conn, "SELECT * FROM deletion_jobs WHERE status <> 'completed' "
                            "OR notified_status IS NULL OR notified_status <> status")


async def get_job(conn: Conn, job_id: int) -> aiosqlite.Row | None:
    return await _one(conn, "SELECT * FROM deletion_jobs WHERE id = ?", (job_id,))


async def set_job_status(conn: Conn, job_id: int, status: str, notified_status: str | None = None) -> None:
    completed = utcnow() if status == "completed" else None
    await conn.execute("UPDATE deletion_jobs SET status = ?, completed_at = COALESCE(?, completed_at), "
                       "notified_status = COALESCE(?, notified_status) WHERE id = ?",
                       (status, completed, notified_status, job_id))


# ───────────────────────────── settings ─────────────────────────────

async def get_setting(conn: Conn, key: str) -> str | None:
    return await _scalar(conn, "SELECT value FROM settings WHERE key = ?", (key,))


async def set_setting(conn: Conn, key: str, value: str, updated_by: int | None) -> None:
    await conn.execute("""INSERT INTO settings (key, value, updated_by, updated_at) VALUES (?,?,?,?)
                          ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by,
                          updated_at = excluded.updated_at""", (key, value, updated_by, utcnow()))
