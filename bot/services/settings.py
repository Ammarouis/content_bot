"""Runtime settings stored in the database (support username).

Content protection is intentionally NOT a setting: it is a permanent rule defined in ``bot/policy.py``.
"""
from __future__ import annotations

from bot.db import repositories as repo
from bot.db.database import Database
from bot.models import Role
from bot.permissions import require_role
from bot.services import validators as v

SUPPORT_USERNAME = "support_username"


class SettingsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def support_username(self) -> str | None:
        async with self.db.read() as c:
            return await repo.get_setting(c, SUPPORT_USERNAME)

    async def set_support_username(self, actor_id: int, value: str) -> str:
        username = v.support_username(value)
        async with self.db.tx() as c:
            await require_role(c, actor_id, Role.ADMIN.value)
            await repo.set_setting(c, SUPPORT_USERNAME, username, actor_id)
        return username
