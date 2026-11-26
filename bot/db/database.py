"""SQLite access layer: one shared connection, serialized short transactions.

Rule: never hold a transaction open across a Telegram API call.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 3


async def _migrate_v2(conn: aiosqlite.Connection) -> None:
    """v1 → v2: subject semesters, per-file protection tracking, unified protection settings."""
    await conn.execute("ALTER TABLE subjects ADD COLUMN semester INTEGER NOT NULL DEFAULT 1 "
                       "CHECK (semester IN (1, 2))")
    await conn.execute("ALTER TABLE subjects ADD COLUMN semester_confirmed INTEGER NOT NULL DEFAULT 1 "
                       "CHECK (semester_confirmed IN (0, 1))")
    # Existing subjects keep all their data; they are placed in semester 1 and flagged for admin review.
    await conn.execute("UPDATE subjects SET semester_confirmed = 0")
    await conn.execute("ALTER TABLE content_files ADD COLUMN protect_requested INTEGER NOT NULL DEFAULT 0 "
                       "CHECK (protect_requested IN (0, 1))")
    await conn.execute("ALTER TABLE content_files ADD COLUMN protected INTEGER CHECK (protected IN (0, 1))")
    async with conn.execute("SELECT COUNT(*) FROM settings WHERE key IN ('protect_forwarding', 'protect_saving') "
                            "AND value = '1'") as cur:
        old_enabled = 1 if (await cur.fetchone())[0] else 0
    # Best knowledge of how v1 posted existing files; the actual flag stays NULL (unknown) until re-published.
    await conn.execute("UPDATE content_files SET protect_requested = ?", (old_enabled,))
    now = utcnow()
    for key, value in (("protection_enabled", str(old_enabled)), ("protection_audience", "all")):
        await conn.execute("INSERT OR IGNORE INTO settings (key, value, updated_by, updated_at) VALUES (?,?,NULL,?)",
                           (key, value, now))
    await conn.execute("DELETE FROM settings WHERE key IN ('protect_forwarding', 'protect_saving')")


async def _migrate_v3(conn: aiosqlite.Connection) -> None:
    """v2 → v3: student protection became a permanent, hardcoded rule (bot/policy.py) — drop its settings.

    File rows keep ``protect_requested``/``protected``; files posted under the old configurable policy are
    re-published to match the permanent rule by the protection sync worker.
    """
    await conn.execute("DELETE FROM settings WHERE key IN ('protection_enabled', 'protection_audience', "
                       "'protection_sync_pending', 'protect_forwarding', 'protect_saving')")


# Ordered migrations: target version -> coroutine. Each runs in its own transaction.
MIGRATIONS = {2: _migrate_v2, 3: _migrate_v3}


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def utc_offset(**delta: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self._lookup: aiosqlite.Connection | None = None   # lock-free read-only connection for role lookups

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode = WAL")
            await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._migrate()
        await self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        await self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        if self.path != ":memory:":
            self._lookup = await aiosqlite.connect(f"file:{Path(self.path).resolve()}?mode=ro", uri=True)
            await self._lookup.execute("PRAGMA busy_timeout = 5000")
        log.info("database_ready", extra={"ctx": {"path": self.path, "schema_version": SCHEMA_VERSION}})

    async def _migrate(self) -> None:
        conn = self.conn
        async with conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'subjects'") as cur:
            existing = await cur.fetchone() is not None
        if not existing:
            return  # fresh database: schema.sql creates the latest version directly
        async with conn.execute("PRAGMA user_version") as cur:
            version = max(1, (await cur.fetchone())[0])
        if version >= SCHEMA_VERSION:
            return
        if self.path != ":memory:":
            backup = f"{self.path}.v{version}.bak"
            if not Path(backup).exists():
                await conn.execute("VACUUM INTO ?", (backup,))   # consistent snapshot before altering anything
                log.info("database_backup_created", extra={"ctx": {"path": backup}})
        for target in sorted(MIGRATIONS):
            if target <= version:
                continue
            await conn.execute("BEGIN IMMEDIATE")
            try:
                await MIGRATIONS[target](conn)
                await conn.execute(f"PRAGMA user_version = {target}")
            except BaseException:
                await conn.execute("ROLLBACK")
                log.exception("database_migration_failed", extra={"ctx": {"target": target}})
                raise
            await conn.execute("COMMIT")
            log.info("database_migrated", extra={"ctx": {"from": version, "to": target}})
            version = target

    async def close(self) -> None:
        if self._lookup is not None:
            await self._lookup.close()
            self._lookup = None
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def role_of(self, telegram_id: int) -> str | None:
        """Current role of a user, for the outgoing-request protection guard.

        Uses a separate read-only connection (WAL readers never block), so it is safe to call while another task
        holds the write lock — e.g. a Telegram call made inside a transaction can never deadlock on it.
        """
        conn = self._lookup or self.conn      # ':memory:' (tests only): shared connection, no lock needed for a read
        async with conn.execute("SELECT role FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[aiosqlite.Connection]:
        """Atomic write transaction (BEGIN IMMEDIATE ... COMMIT / ROLLBACK)."""
        async with self._lock:
            conn = self.conn
            await conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                await conn.execute("ROLLBACK")
                raise
            else:
                await conn.execute("COMMIT")

    @asynccontextmanager
    async def read(self) -> AsyncIterator[aiosqlite.Connection]:
        """Consistent read access (serialized with writes on the shared connection)."""
        async with self._lock:
            yield self.conn
