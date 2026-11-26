"""Configuration loaded exclusively from environment variables (optionally a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _req(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _int(name: str, default: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        if default is None:
            raise ConfigError(f"Missing required environment variable: {name}")
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {name} must be an integer") from exc


@dataclass(frozen=True)
class Channels:
    temp_pdf: int
    temp_tex: int
    approved_pdf: int
    approved_tex: int

    def temp_for(self, kind: str) -> int:
        return self.temp_pdf if kind == "pdf" else self.temp_tex

    def approved_for(self, kind: str) -> int:
        return self.approved_pdf if kind == "pdf" else self.approved_tex

    def all(self) -> dict[str, int]:
        return {
            "temp_pdf": self.temp_pdf,
            "temp_tex": self.temp_tex,
            "approved_pdf": self.approved_pdf,
            "approved_tex": self.approved_tex,
        }


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    channels: Channels
    database_path: str = "data/itgenix.db"
    log_level: str = "INFO"
    log_format: str = "json"
    display_timezone: str = "Asia/Damascus"
    max_pdf_bytes: int = 50 * 1024 * 1024
    max_tex_bytes: int = 10 * 1024 * 1024
    cleanup_interval_seconds: int = 30
    cleanup_max_attempts: int = 12
    preview_ttl_hours: int = 24
    stale_operation_minutes: int = 10

    @classmethod
    def from_env(cls) -> "Config":
        admin_raw = _req("ADMIN_IDS")
        try:
            admin_ids = frozenset(int(x) for x in admin_raw.replace(" ", "").split(",") if x)
        except ValueError as exc:
            raise ConfigError("ADMIN_IDS must be comma separated integers") from exc
        if not admin_ids:
            raise ConfigError("ADMIN_IDS must contain at least one Telegram ID")
        channels = Channels(
            temp_pdf=_int("TEMP_PDF_CHANNEL_ID"),
            temp_tex=_int("TEMP_TEX_CHANNEL_ID"),
            approved_pdf=_int("APPROVED_PDF_CHANNEL_ID"),
            approved_tex=_int("APPROVED_TEX_CHANNEL_ID"),
        )
        if len(set(channels.all().values())) != 4:
            raise ConfigError("The four channel IDs must be distinct")
        log_format = os.environ.get("LOG_FORMAT", "json").strip().lower()
        if log_format not in {"json", "text"}:
            raise ConfigError("LOG_FORMAT must be 'json' or 'text'")
        return cls(
            bot_token=_req("BOT_TOKEN"),
            admin_ids=admin_ids,
            channels=channels,
            database_path=os.environ.get("DATABASE_PATH", "data/itgenix.db").strip(),
            log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper(),
            log_format=log_format,
            display_timezone=os.environ.get("DISPLAY_TIMEZONE", "Asia/Damascus").strip(),
            max_pdf_bytes=_int("MAX_PDF_SIZE_MB", 50) * 1024 * 1024,
            max_tex_bytes=_int("MAX_TEX_SIZE_MB", 10) * 1024 * 1024,
            cleanup_interval_seconds=max(5, _int("CLEANUP_INTERVAL_SECONDS", 30)),
            cleanup_max_attempts=max(1, _int("CLEANUP_MAX_ATTEMPTS", 12)),
            preview_ttl_hours=min(40, max(1, _int("PREVIEW_TTL_HOURS", 24))),
            stale_operation_minutes=max(2, _int("STALE_OPERATION_MINUTES", 10)),
        )
