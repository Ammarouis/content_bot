"""Role-based access control: router filters (handler layer) and DB re-checks (service layer)."""
from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter

from bot.db import repositories as repo
from bot.models import AppUser, Role
from bot.services.errors import PermissionDenied

REVIEWERS = (Role.UPLOADER.value, Role.ADMIN.value)


class HasRole(BaseFilter):
    """Router-level filter. ``user`` is injected by AuthMiddleware from the database."""

    def __init__(self, *roles: str) -> None:
        self.roles = frozenset(roles)

    async def __call__(self, event: Any, user: AppUser | None = None) -> bool:
        return user is not None and user.role in self.roles


async def require_role(conn, telegram_id: int, *roles: str) -> AppUser:
    """Service-level re-check against the current database state (defence in depth)."""
    user = await repo.get_user(conn, telegram_id)
    if user is None or user.role not in roles:
        raise PermissionDenied()
    return user
