from aiogram import Router, types
from aiogram.filters import Command

from app.config import Config
from app.db import Database
from app.models import User
from app.services import cycles
from app.services import reports as reports_service

router = Router()


def _is_owner_or_admin(user: User | None) -> bool:
    return bool(user and user.role in ("owner", "admin"))


@router.message(Command("report"))
async def cmd_report(message: types.Message, user: User, db: Database, config: Config):
    if not _is_owner_or_admin(user):
        return
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        await message.answer("Немає відкритого циклу.")
        return
    xlsx, pdf, summary = await reports_service.generate_report(
        db, cycle.id, config.clinic_name, config.reports_dir
    )
    await message.answer(summary, parse_mode="Markdown")
    await message.answer_document(types.FSInputFile(str(xlsx)))
    await message.answer_document(types.FSInputFile(str(pdf)))


@router.message(Command("history"))
async def cmd_history(message: types.Message, user: User, db: Database):
    if not _is_owner_or_admin(user):
        return
    rows = await cycles.list_recent_cycles(db, limit=10)
    if not rows:
        await message.answer("Історія порожня.")
        return
    lines = ["*Останні цикли*", ""]
    for c in rows:
        status = "🟢" if c.status == "open" else "⚪️"
        closed = c.closed_at or "—"
        lines.append(f"{status} #{c.id} | {c.opened_at} → {closed}")
    lines += ["", "Отримати файли: /get <cycle_id>"]
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("get"))
async def cmd_get(message: types.Message, user: User, db: Database):
    if not _is_owner_or_admin(user):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: `/get <cycle_id>`", parse_mode="Markdown")
        return
    cycle_id = int(parts[1])
    rep = await reports_service.latest_report(db, cycle_id)
    if not rep:
        await message.answer("Звіт по цьому циклу не сформовано.")
        return
    await message.answer(rep["summary_text"], parse_mode="Markdown")
    try:
        await message.answer_document(types.FSInputFile(rep["xlsx_path"]))
        await message.answer_document(types.FSInputFile(rep["pdf_path"]))
    except FileNotFoundError:
        await message.answer("⚠️ Файли звіту не знайдено на диску.")
