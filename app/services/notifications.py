import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from app.db import Database

log = logging.getLogger(__name__)


async def _users_by_role(db: Database, role: str) -> list[int]:
    cur = await db.conn.execute("SELECT tg_id FROM users WHERE role = ?", (role,))
    rows = await cur.fetchall()
    return [r["tg_id"] for r in rows]


async def send_report_to_owners(
    bot: Bot, db: Database, summary: str, xlsx: Path, pdf: Path
) -> None:
    targets = await _users_by_role(db, "owner")
    for tg_id in targets:
        try:
            await bot.send_message(tg_id, summary, parse_mode="Markdown")
            await bot.send_document(tg_id, FSInputFile(str(xlsx)))
            await bot.send_document(tg_id, FSInputFile(str(pdf)))
        except Exception as e:
            log.exception("Failed to send report to owner %s: %s", tg_id, e)


async def notify_admins(bot: Bot, db: Database, text: str) -> None:
    targets = await _users_by_role(db, "admin")
    for tg_id in targets:
        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
        except Exception as e:
            log.exception("Failed to notify admin %s: %s", tg_id, e)
