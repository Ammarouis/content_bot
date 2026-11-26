"""Application assembly: bot, dispatcher, routers, middlewares, background worker."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, ErrorEvent

from bot import texts
from bot.config import Config
from bot.db.database import Database
from bot.handlers import admin_academic, admin_content, admin_settings, admin_users, common, review, student
from bot.middlewares.auth import AuthMiddleware
from bot.services.container import Services, build_services

log = logging.getLogger(__name__)


def create_bot(config: Config, **kwargs) -> Bot:
    return Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                                              link_preview_is_disabled=True), **kwargs)


def create_dispatcher(svc: Services) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), svc=svc)
    auth = AuthMiddleware(svc.users)
    dp.message.outer_middleware(auth)
    dp.callback_query.outer_middleware(auth)
    # Order matters: role routers are filtered by HasRole; the fallback router must be last.
    dp.include_routers(common.router, student.router, review.router, admin_users.router, admin_academic.router,
                       admin_content.router, admin_settings.router, common.fallback_router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.error("handler_error", exc_info=event.exception,
                  extra={"ctx": {"update_id": event.update.update_id}})
        upd = event.update
        try:
            if upd.callback_query:
                await upd.callback_query.answer(texts.UNEXPECTED_ERROR, show_alert=True)
            elif upd.message:
                await upd.message.answer(texts.UNEXPECTED_ERROR)
        except Exception:
            pass
        return True

    return dp


async def run(config: Config) -> None:
    texts.set_timezone(config.display_timezone)
    db = Database(config.database_path)
    await db.connect()
    bot = create_bot(config)
    svc = build_services(config, db, bot)
    await svc.users.bootstrap()
    rolled = await svc.cleanup.recover(stale_only=False)  # nothing is in flight at startup
    if rolled:
        log.warning("startup_recovery", extra={"ctx": {"rolled_back": rolled}})
    dp = create_dispatcher(svc)

    await bot.set_my_commands([BotCommand(command="start", description="القائمة الرئيسية")],
                              scope=BotCommandScopeDefault())
    stop = asyncio.Event()
    worker = asyncio.create_task(svc.cleanup.run_forever(config.cleanup_interval_seconds, stop))
    try:
        log.info("bot_started")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"], handle_signals=True)
    finally:
        stop.set()
        await worker
        await bot.session.close()
        await db.close()
        log.info("bot_stopped")
