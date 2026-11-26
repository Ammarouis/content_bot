"""Academic hierarchy: years (fixed 1-5), specializations (years 4-5) and subjects."""
from __future__ import annotations

import logging
import sqlite3

from bot.db import repositories as repo
from bot.db.database import Database
from bot.models import Role, Specialization, Subject, Year
from bot.permissions import require_role
from bot.services import validators as v
from bot.services.errors import DomainError

log = logging.getLogger(__name__)


def _integrity_code(exc: sqlite3.IntegrityError) -> str:
    msg = str(exc)
    for code in ("specialization_required", "specialization_not_allowed", "specialization_year_mismatch",
                 "year_has_no_specializations"):
        if code in msg:
            return code
    if "subjects.code" in msg:
        return "subject_code_exists"
    if "specializations.year_id, specializations.name" in msg:
        return "specialization_exists"
    if "FOREIGN KEY" in msg:
        return "in_use"
    return "integrity_error"


class AcademicService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def years(self) -> list[Year]:
        async with self.db.read() as c:
            return await repo.list_years(c)

    async def year(self, year_id: int) -> Year:
        async with self.db.read() as c:
            y = await repo.get_year(c, year_id)
        if not y:
            raise DomainError("year_not_found")
        return y

    async def specializations(self, year_id: int) -> list[Specialization]:
        async with self.db.read() as c:
            return await repo.list_specializations(c, year_id)

    async def specialization(self, spec_id: int) -> Specialization:
        async with self.db.read() as c:
            s = await repo.get_specialization(c, spec_id)
        if not s:
            raise DomainError("specialization_not_found")
        return s

    async def add_specialization(self, actor_id: int, year_id: int, name: str) -> int:
        name = v.clean_text(name, min_len=2, max_len=100, code="invalid_name")
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            year = await repo.get_year(c, year_id)
            if not year:
                raise DomainError("year_not_found")
            if not year.requires_specialization:
                raise DomainError("year_has_no_specializations")
            try:
                return await repo.insert_specialization(c, year_id, name)
            except sqlite3.IntegrityError as exc:
                raise DomainError(_integrity_code(exc)) from exc

    async def rename_specialization(self, actor_id: int, spec_id: int, name: str) -> None:
        name = v.clean_text(name, min_len=2, max_len=100, code="invalid_name")
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            try:
                if not await repo.rename_specialization(c, spec_id, name):
                    raise DomainError("specialization_not_found")
            except sqlite3.IntegrityError as exc:
                raise DomainError(_integrity_code(exc)) from exc

    async def delete_specialization(self, actor_id: int, spec_id: int) -> None:
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            if await repo.count_subjects_in_spec(c, spec_id):
                raise DomainError("specialization_has_subjects")
            if not await repo.delete_specialization(c, spec_id):
                raise DomainError("specialization_not_found")

    # ── subjects ──
    async def subjects(self, year_id: int, spec_id: int | None, semester: int | None = None) -> list[Subject]:
        async with self.db.read() as c:
            return await repo.list_subjects(c, year_id, spec_id, semester)

    async def unconfirmed_subjects(self) -> list[Subject]:
        async with self.db.read() as c:
            return await repo.unconfirmed_subjects(c)

    async def subject(self, subject_id: int) -> Subject:
        async with self.db.read() as c:
            s = await repo.get_subject(c, subject_id)
        if not s:
            raise DomainError("subject_not_found")
        return s

    async def subject_by_code(self, code: str) -> Subject:
        code = v.subject_code(code)
        async with self.db.read() as c:
            s = await repo.get_subject_by_code(c, code)
        if not s:
            raise DomainError("subject_not_found")
        return s

    async def subject_stats(self, subject_id: int) -> dict:
        async with self.db.read() as c:
            return await repo.subject_stats(c, subject_id)

    async def create_subject(self, actor_id: int, year_id: int, spec_id: int | None, semester: int, name: str,
                             code: str) -> int:
        semester = v.semester(semester)
        name = v.clean_text(name, min_len=2, max_len=150, code="invalid_subject_name")
        code = v.subject_code(code)
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            try:
                sid = await repo.insert_subject(c, code, name, year_id, spec_id, semester)
            except sqlite3.IntegrityError as exc:
                raise DomainError(_integrity_code(exc)) from exc
        log.info("subject_created", extra={"ctx": {"actor": actor_id, "subject": sid, "code": code}})
        return sid

    async def update_subject(self, actor_id: int, subject_id: int, field: str, value: str | int) -> None:
        if field == "name":
            value = v.clean_text(value, min_len=2, max_len=150, code="invalid_subject_name")
        elif field == "code":
            value = v.subject_code(value)
        elif field == "semester":   # setting (or re-confirming) the semester also clears the migration flag
            value = v.semester(value)
        else:
            raise DomainError("invalid_field")
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            try:
                if not await repo.update_subject_field(c, subject_id, field, value):
                    raise DomainError("subject_not_found")
            except sqlite3.IntegrityError as exc:
                raise DomainError(_integrity_code(exc)) from exc

    async def delete_subject(self, actor_id: int, subject_id: int) -> None:
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            stats = await repo.subject_stats(c, subject_id)
            if stats["contents"]:
                raise DomainError("subject_has_content")
            try:
                if not await repo.delete_subject(c, subject_id):
                    raise DomainError("subject_not_found")
            except sqlite3.IntegrityError as exc:
                raise DomainError(_integrity_code(exc)) from exc
        log.info("subject_deleted", extra={"ctx": {"actor": actor_id, "subject": subject_id}})
