"""Wires services together (single place for dependency construction)."""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from bot.config import Config
from bot.db.database import Database
from bot.services.academic import AcademicService
from bot.services.cleanup import CleanupService
from bot.services.content import ContentService
from bot.policy import StudentProtectionMiddleware
from bot.services.protection import ProtectionService
from bot.services.settings import SettingsService
from bot.services.telegram_gateway import TelegramGateway
from bot.services.users import UserService


@dataclass
class Services:
    config: Config
    db: Database
    gateway: TelegramGateway
    users: UserService
    academic: AcademicService
    settings: SettingsService
    cleanup: CleanupService
    content: ContentService
    protection: ProtectionService


def build_services(config: Config, db: Database, bot: Bot) -> Services:
    from bot.notifications import TelegramNotifier  # UI-layer implementation of the Notifier port

    gateway = TelegramGateway(bot)
    notifier = TelegramNotifier(gateway)
    settings = SettingsService(db)
    cleanup = CleanupService(db, gateway, max_attempts=config.cleanup_max_attempts,
                             preview_ttl_hours=config.preview_ttl_hours,
                             stale_minutes=config.stale_operation_minutes, notifier=notifier)
    # permanent student protection: enforced on every outgoing Bot API request (see bot/policy.py)
    bot.session.middleware(StudentProtectionMiddleware(db, config.channels, config.admin_ids))
    protection = ProtectionService(db, gateway, cleanup)
    cleanup.periodic.append(protection.sync_tick)
    return Services(
        config=config, db=db, gateway=gateway,
        users=UserService(db, config.admin_ids),
        academic=AcademicService(db),
        settings=settings,
        cleanup=cleanup,
        content=ContentService(db, gateway, config.channels, cleanup, notifier),
        protection=protection,
    )
