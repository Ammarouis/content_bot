"""In-memory fake of the Bot API used for end-to-end handler tests (no network)."""
from __future__ import annotations

import itertools
from datetime import datetime, timezone
from typing import Callable

from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery, CopyMessage, DeleteMessage, EditMessageText, GetChat, GetChatMember, GetMe, SendDocument,
    SendMessage, SetMyCommands,
)
from aiogram.types import ChatFullInfo, ChatMemberAdministrator, Message, MessageId, User

BOT_ID = 4242


class FakeTelegram(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list = []
        self._ids = itertools.count(5000)
        self.messages: dict[tuple[int, int], dict] = {}   # (chat_id, message_id) -> info (existing messages)
        self.deleted: list[tuple[int, int]] = []
        self.failures: list[Callable[[object], Exception | None]] = []
        self.protected_chats: set[int] = set()   # chats with channel-level "restrict saving content"
        self.ignore_protection = False

    # helpers for tests
    def fail_when(self, rule: Callable[[object], bool], message: str = "Bad Request: forced failure") -> Callable:
        def check(method):
            return TelegramBadRequest(method=method, message=message) if rule(method) else None
        self.failures.append(check)
        return check

    def clear_failures(self) -> None:
        self.failures.clear()

    def in_chat(self, chat_id: int) -> list[tuple[int, int]]:
        return [k for k in self.messages if k[0] == chat_id]

    def of(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]

    def documents_in(self, chat_id: int) -> list[dict]:
        """Existing document messages in a chat (e.g. channel posts or preview copies)."""
        return [m for (c, _), m in self.messages.items() if c == chat_id and "document" in m]

    def _msg(self, bot, chat_id: int, protected: bool = False, **extra) -> Message:
        mid = next(self._ids)
        chat_type = "channel" if chat_id < 0 else "private"
        # like the real API: has_protected_content is present only when the message is protected
        if protected or chat_id in self.protected_chats:
            extra["has_protected_content"] = True
        data = {"message_id": mid, "date": datetime.now(timezone.utc), "chat": {"id": chat_id, "type": chat_type},
                "from": {"id": BOT_ID, "is_bot": True, "first_name": "bot"}, **extra}
        self.messages[(chat_id, mid)] = extra
        return Message.model_validate(data, context={"bot": bot})

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        for check in self.failures:
            exc = check(method)
            if exc:
                raise exc
        if isinstance(method, SendMessage):
            return self._msg(bot, method.chat_id, protected=bool(method.protect_content), text=method.text)
        if isinstance(method, EditMessageText):
            return Message.model_validate({"message_id": method.message_id, "date": datetime.now(timezone.utc),
                                           "chat": {"id": method.chat_id, "type": "private"}, "text": method.text},
                                          context={"bot": bot})
        if isinstance(method, SendDocument):
            if self.ignore_protection:   # simulate an API response that does not confirm protect_content
                return self._msg(bot, method.chat_id, caption=method.caption,
                                 document={"file_id": method.document, "file_unique_id": "u" + str(method.document)})
            return self._msg(bot, method.chat_id, protected=bool(method.protect_content), caption=method.caption,
                             document={"file_id": method.document, "file_unique_id": "u" + str(method.document)},
                             silent=bool(method.disable_notification))
        if isinstance(method, CopyMessage):
            src = (method.from_chat_id, method.message_id)
            if src not in self.messages:
                raise TelegramBadRequest(method=method, message="Bad Request: message to copy not found")
            msg = self._msg(bot, method.chat_id, protected=bool(method.protect_content), copied_from=src,
                            caption=method.caption)
            return MessageId(message_id=msg.message_id)
        if isinstance(method, DeleteMessage):
            key = (method.chat_id, method.message_id)
            if key not in self.messages:
                raise TelegramBadRequest(method=method, message="Bad Request: message to delete not found")
            del self.messages[key]
            self.deleted.append(key)
            return True
        if isinstance(method, (AnswerCallbackQuery, SetMyCommands)):
            return True
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="bot", username="itgx_bot")
        if isinstance(method, GetChat):
            return ChatFullInfo.model_construct(id=method.chat_id, type="channel", title=f"ch{method.chat_id}",
                                                has_protected_content=True)
        if isinstance(method, GetChatMember):
            return ChatMemberAdministrator.model_construct(status="administrator", can_post_messages=True,
                                                           can_delete_messages=True)
        raise NotImplementedError(type(method).__name__)

    async def stream_content(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        pass
