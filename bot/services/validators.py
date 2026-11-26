"""Pure input validation helpers (no I/O)."""
from __future__ import annotations

import re

from bot.services.errors import DomainError

_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,19}$")
_SUPPORT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def clean_text(value: str | None, *, min_len: int, max_len: int, code: str) -> str:
    text = " ".join((value or "").split())
    if not (min_len <= len(text) <= max_len):
        raise DomainError(code, min=min_len, max=max_len)
    return text


def telegram_id(value: str | None) -> int:
    raw = (value or "").strip()
    if not raw.isdigit() or not (5 <= len(raw) <= 15):
        raise DomainError("invalid_telegram_id")
    return int(raw)


def subject_code(value: str | None) -> str:
    code = (value or "").strip().upper()
    if not _CODE_RE.fullmatch(code):
        raise DomainError("invalid_subject_code")
    return code


def content_number(value: str | None) -> int:
    raw = (value or "").strip()
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    raw = raw.translate(trans)
    if not raw.isdigit() or not (1 <= int(raw) <= 9999):
        raise DomainError("invalid_number")
    return int(raw)


def semester(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise DomainError("invalid_semester") from None
    if number not in (1, 2):
        raise DomainError("invalid_semester")
    return number


def support_username(value: str | None) -> str:
    raw = (value or "").strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
    if not _SUPPORT_RE.fullmatch(raw):
        raise DomainError("invalid_support_username")
    return raw


def document(file_name: str | None, mime: str | None, size: int | None, kind: str, max_bytes: int) -> None:
    name = (file_name or "").lower()
    if kind == "pdf":
        if not (name.endswith(".pdf") or mime == "application/pdf"):
            raise DomainError("invalid_pdf")
    elif not name.endswith(".tex"):
        raise DomainError("invalid_tex")
    if size and size > max_bytes:
        raise DomainError("file_too_large", max_mb=max_bytes // (1024 * 1024))
