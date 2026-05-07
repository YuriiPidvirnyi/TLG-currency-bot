import logging
from pathlib import Path

import aiosqlite

log = logging.getLogger(__name__)


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected")
        return self._conn

    async def apply_migrations(self, migrations_dir: Path) -> None:
        await self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        await self.conn.commit()

        applied = {
            row["name"]
            async for row in await self.conn.execute("SELECT name FROM schema_migrations")
        }

        for path in sorted(migrations_dir.glob("*.sql")):
            if path.name in applied:
                continue
            log.info("Applying migration %s", path.name)
            sql = path.read_text(encoding="utf-8")
            await self.conn.executescript(sql)
            await self.conn.execute(
                "INSERT INTO schema_migrations (name) VALUES (?)", (path.name,)
            )
            await self.conn.commit()

    async def seed_initial_admin(self, tg_id: int) -> None:
        if not tg_id:
            return
        cur = await self.conn.execute("SELECT 1 FROM users WHERE tg_id = ?", (tg_id,))
        if await cur.fetchone():
            return
        await self.conn.execute(
            "INSERT INTO users (tg_id, full_name, role) VALUES (?, ?, 'admin')",
            (tg_id, "Адміністратор"),
        )
        await self.conn.commit()
        log.info("Seeded initial admin tg_id=%s", tg_id)

    async def seed_owner(self, tg_id: int) -> None:
        if not tg_id:
            return
        cur = await self.conn.execute("SELECT role FROM users WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute(
                "INSERT INTO users (tg_id, full_name, role) VALUES (?, ?, 'owner')",
                (tg_id, "Власниця"),
            )
            await self.conn.commit()
            log.info("Seeded owner tg_id=%s", tg_id)
