"""User management and student-subject assignments."""
from __future__ import annotations

import logging
import sqlite3

from bot.db import repositories as repo
from bot.db.database import Database
from bot.models import AppUser, Role, Subject
from bot.permissions import require_role
from bot.services import validators as v
from bot.services.errors import DomainError

log = logging.getLogger(__name__)
ROLES = {r.value for r in Role}


class UserService:
    def __init__(self, db: Database, bootstrap_admins: frozenset[int]) -> None:
        self.db = db
        self.bootstrap_admins = bootstrap_admins

    async def bootstrap(self) -> None:
        async with self.db.tx() as c:
            for tid in self.bootstrap_admins:
                await repo.upsert_bootstrap_admin(c, tid)

    async def get(self, telegram_id: int) -> AppUser | None:
        async with self.db.read() as c:
            return await repo.get_user(c, telegram_id)

    async def list(self, role: str | None, page: int, per_page: int) -> tuple[list[AppUser], int]:
        async with self.db.read() as c:
            return await repo.list_users(c, role, per_page, page * per_page)

    async def add(self, actor_id: int, telegram_id: int, full_name: str, role: str) -> AppUser:
        if role not in ROLES:
            raise DomainError("invalid_role")
        name = v.clean_text(full_name, min_len=2, max_len=100, code="invalid_name")
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            if await repo.get_user(c, telegram_id):
                raise DomainError("user_exists")
            await repo.insert_user(c, telegram_id, name, role, actor_id)
            user = await repo.get_user(c, telegram_id)
        log.info("user_added", extra={"ctx": {"actor": actor_id, "target": telegram_id, "role": role}})
        return user

    def _guard_target(self, actor_id: int, target_id: int) -> None:
        if target_id in self.bootstrap_admins:
            raise DomainError("protected_admin")
        if target_id == actor_id:
            raise DomainError("cannot_modify_self")

    async def change_role(self, actor_id: int, target_id: int, role: str) -> AppUser:
        if role not in ROLES:
            raise DomainError("invalid_role")
        self._guard_target(actor_id, target_id)
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            target = await repo.get_user(c, target_id)
            if not target:
                raise DomainError("user_not_found")
            await repo.update_user_role(c, target_id, role)
            if role != Role.STUDENT.value:
                await repo.clear_student_subjects(c, target_id)
            user = await repo.get_user(c, target_id)
        log.info("user_role_changed", extra={"ctx": {"actor": actor_id, "target": target_id, "role": role}})
        return user

    async def rename(self, actor_id: int, target_id: int, full_name: str) -> AppUser:
        name = v.clean_text(full_name, min_len=2, max_len=100, code="invalid_name")
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            if not await repo.update_user_name(c, target_id, name):
                raise DomainError("user_not_found")
            return await repo.get_user(c, target_id)

    async def remove(self, actor_id: int, target_id: int) -> None:
        self._guard_target(actor_id, target_id)
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            try:
                if not await repo.delete_user(c, target_id):
                    raise DomainError("user_not_found")
            except sqlite3.IntegrityError as exc:
                raise DomainError("user_delete_blocked") from exc
        log.info("user_removed", extra={"ctx": {"actor": actor_id, "target": target_id}})

    # ── student subjects ──
    async def student_subjects(self, student_id: int) -> list[Subject]:
        async with self.db.read() as c:
            return await repo.student_subjects(c, student_id)

    async def student_subject_ids(self, student_id: int) -> set[int]:
        async with self.db.read() as c:
            return await repo.student_subject_ids(c, student_id)

    async def toggle_assignment(self, actor_id: int, student_id: int, subject_id: int) -> bool:
        """Returns True if the subject is assigned after the call."""
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            target = await repo.get_user(c, student_id)
            if not target or target.role != Role.STUDENT.value:
                raise DomainError("not_a_student")
            if not await repo.get_subject(c, subject_id):
                raise DomainError("subject_not_found")
            if await repo.is_assigned(c, student_id, subject_id):
                await repo.unassign_subject(c, student_id, subject_id)
                return False
            await repo.assign_subject(c, student_id, subject_id)
            return True
