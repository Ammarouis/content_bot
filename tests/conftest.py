from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import Update

from bot.app import create_bot, create_dispatcher
from bot.config import Channels, Config
from bot.db.database import Database
from bot.services.container import Services, build_services
from tests.fake_telegram import FakeTelegram

ADMIN = 1000001
UPLOADER = 2000002
STUDENT = 3000003
STUDENT2 = 3000004
STRANGER = 9000009
CH = Channels(temp_pdf=-1001, temp_tex=-1002, approved_pdf=-1003, approved_tex=-1004)


@dataclass
class Env:
    svc: Services
    tg: FakeTelegram
    dp: object
    bot: object
    _ids = itertools.count(1)

    async def _feed(self, payload: dict) -> None:
        payload["update_id"] = next(self._ids)
        await self.dp.feed_update(self.bot, Update.model_validate(payload, context={"bot": self.bot}))

    def _message(self, uid: int, **extra) -> dict:
        return {"message_id": next(self._ids), "date": datetime.now(timezone.utc),
                "chat": {"id": uid, "type": "private"},
                "from": {"id": uid, "is_bot": False, "first_name": f"u{uid}"}, **extra}

    async def text(self, uid: int, text: str) -> None:
        await self._feed({"message": self._message(uid, text=text)})

    async def doc(self, uid: int, name: str, mime: str = "application/octet-stream", size: int = 1000,
                  file_id: str | None = None) -> None:
        file_id = file_id or f"F_{name}_{next(self._ids)}"
        await self._feed({"message": self._message(uid, document={"file_id": file_id, "file_unique_id": "U" + file_id,
                                                                  "file_name": name, "mime_type": mime,
                                                                  "file_size": size})})

    async def click(self, uid: int, data) -> None:
        packed = data.pack() if hasattr(data, "pack") else data
        await self._feed({"callback_query": {"id": str(next(self._ids)), "chat_instance": "ci", "data": packed,
                                             "from": {"id": uid, "is_bot": False, "first_name": f"u{uid}"},
                                             "message": self._message(uid, text="menu")}})

    def outputs(self, uid: int) -> list:
        return [c for c in self.tg.calls if isinstance(c, (SendMessage, EditMessageText)) and c.chat_id == uid]

    def last(self, uid: int):
        out = self.outputs(uid)
        assert out, f"no output for {uid}"
        return out[-1]

    def last_text(self, uid: int) -> str:
        return self.last(uid).text

    def buttons(self, uid: int) -> dict[str, str]:
        markup = self.last(uid).reply_markup
        if not markup:
            return {}
        return {b.text: (b.callback_data or b.url) for row in markup.inline_keyboard for b in row}

    def button(self, uid: int, contains: str) -> str:
        for text, data in self.buttons(uid).items():
            if contains in text:
                return data
        raise AssertionError(f"button containing {contains!r} not found in {list(self.buttons(uid))}")

    def picker(self, uid: int) -> dict[int, tuple[str, str]]:
        """Number buttons currently displayed: number -> (label, action)."""
        from bot.callbacks import St
        out = {}
        for text, data in self.buttons(uid).items():
            if data and data.startswith("s:"):
                cb = St.unpack(data)
                if cb.a in ("nb", "nbx"):
                    out[cb.x] = (text, cb.a)
        return out

    async def pick_number(self, uid: int, number: int) -> None:
        """Press «المزيد» until the number is shown, then press it (exactly like a user would)."""
        from bot import texts
        for _ in range(600):
            shown = self.picker(uid)
            if number in shown:
                break
            await self.click(uid, self.button(uid, texts.BTN_MORE))
        for text, data in self.buttons(uid).items():
            if data and data.startswith("s:") and data.split(":")[2] == str(number) and data.split(":")[1] in ("nb", "nbx"):
                return await self.click(uid, data)
        raise AssertionError(f"number {number} not on picker")

    def alerts(self) -> list[str]:
        from aiogram.methods import AnswerCallbackQuery
        return [c.text for c in self.tg.calls if isinstance(c, AnswerCallbackQuery) and c.text]


def _detach_routers() -> None:
    """Module-level routers attach to one dispatcher per process; tests build a fresh one each time."""
    from bot.handlers import admin_academic, admin_content, admin_settings, admin_users, common, review, student
    for r in (common.router, student.router, review.router, admin_users.router, admin_academic.router,
              admin_content.router, admin_settings.router, common.fallback_router):
        parent = r.parent_router
        if parent is not None:
            parent.sub_routers.remove(r)
            r._parent_router = None


@pytest.fixture
async def env(tmp_path):
    _detach_routers()
    config = Config(bot_token="42:TEST", admin_ids=frozenset({ADMIN}), channels=CH,
                    database_path=str(tmp_path / "test.db"), cleanup_max_attempts=3)
    db = Database(config.database_path)
    await db.connect()
    tg = FakeTelegram()
    bot = create_bot(config, session=tg)
    svc = build_services(config, db, bot)
    await svc.users.bootstrap()
    dp = create_dispatcher(svc)
    yield Env(svc=svc, tg=tg, dp=dp, bot=bot)
    await db.close()


@pytest.fixture
async def seeded(env):
    """Admin + uploader + two students, one subject (year 1) assigned to STUDENT."""
    s = env.svc
    await s.users.add(ADMIN, UPLOADER, "مسؤول الرفع", "uploader")
    await s.users.add(ADMIN, STUDENT, "طالب أول", "student")
    await s.users.add(ADMIN, STUDENT2, "طالب ثان", "student")
    sid = await s.academic.create_subject(ADMIN, 1, None, 1, "برمجة 1", "cs101")
    await s.users.toggle_assignment(ADMIN, STUDENT, sid)
    env.subject_id = sid
    return env


@pytest.fixture(autouse=True)
def no_handler_errors(caplog):
    """Fail any test in which a handler raised (the global error handler would otherwise hide it)."""
    import logging
    caplog.set_level(logging.INFO)
    yield
    errors = [r for r in caplog.records if r.getMessage() in ("handler_error", "cleanup_tick_failed")]
    assert not errors, [f"{r.getMessage()}: {r.exc_info}" for r in errors]
