import logging
import shlex

from aiogram import F, Router, types
from aiogram.filters import Command

from app.config import Config
from app.db import Database
from app.models import User
from app.services import catalog, cycles, notifications
from app.services import reports as reports_service
from app.services import requests as req_service

log = logging.getLogger(__name__)
router = Router()


def _is_admin(user: User | None) -> bool:
    return bool(user and user.role == "admin")


@router.message(Command("open"))
async def cmd_open(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    existing = await cycles.get_open_cycle(db)
    if existing:
        await message.answer(f"Цикл #{existing.id} вже відкритий.")
        return
    cycle = await cycles.open_cycle(db, opened_by_user_id=user.id)
    await message.answer(f"✅ Відкрито цикл #{cycle.id}.")


@router.message(Command("cycle"))
async def cmd_cycle(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        await message.answer("Немає відкритого циклу. /open")
        return
    counts = await cycles.cycle_counts(db, cycle.id)
    await message.answer(
        f"*Цикл #{cycle.id}*\n"
        f"Відкрито: {cycle.opened_at}\n\n"
        f"✅ Підтверджено: {counts['approved']}\n"
        f"⏳ На ревʼю: {counts['pending']}\n"
        f"🚫 Відхилено: {counts['rejected']}",
        parse_mode="Markdown",
    )


@router.message(Command("preview"))
async def cmd_preview(message: types.Message, user: User, db: Database, config: Config):
    if not _is_admin(user) and (not user or user.role != "owner"):
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


@router.message(Command("close"))
async def cmd_close(message: types.Message, user: User, db: Database, config: Config):
    if not _is_admin(user):
        return
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        await message.answer("Немає відкритого циклу.")
        return
    counts = await cycles.cycle_counts(db, cycle.id)
    if counts["pending"]:
        await message.answer(
            f"⏳ Є {counts['pending']} позицій на ревʼю — перегляньте /pending перед закриттям."
        )
        return
    if counts["approved"] == 0:
        await message.answer("Немає підтверджених позицій — закривати нічого.")
        return

    xlsx, pdf, summary = await reports_service.generate_report(
        db, cycle.id, config.clinic_name, config.reports_dir
    )
    await reports_service.save_report_record(db, cycle.id, xlsx, pdf, summary)
    await cycles.close_cycle(db, cycle.id, closed_by_user_id=user.id)

    await message.answer(summary, parse_mode="Markdown")
    await message.answer_document(types.FSInputFile(str(xlsx)))
    await message.answer_document(types.FSInputFile(str(pdf)))

    await notifications.send_report_to_owners(message.bot, db, summary, xlsx, pdf)

    new_cycle = await cycles.open_cycle(db, opened_by_user_id=user.id)
    await message.answer(f"🔁 Відкрито новий цикл #{new_cycle.id}.")


@router.message(Command("pending"))
async def cmd_pending(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        await message.answer("Немає відкритого циклу.")
        return
    rows = await req_service.list_pending_requests(db, cycle.id)
    if not rows:
        await message.answer("Усе підтверджено, нічого ревʼювати.")
        return
    lines = [f"*Pending у циклі #{cycle.id}* ({len(rows)})", ""]
    for r in rows:
        com = f" / {r['comment']}" if r["comment"] else ""
        lines.append(
            f"#{r['id']} • {r['cabinet_name']} • {r['free_form_name']} — "
            f"{r['qty']:g} {r['unit']} ({r['author']}){com}"
        )
    lines += ["", "Команди: /approve <id>, /reject <id>, /allapprove"]
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("approve"))
async def cmd_approve(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: `/approve <id>`", parse_mode="Markdown")
        return
    await req_service.set_status(db, int(parts[1]), "approved")
    await message.answer("✅ Підтверджено.")


@router.message(Command("reject"))
async def cmd_reject(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: `/reject <id>`", parse_mode="Markdown")
        return
    await req_service.set_status(db, int(parts[1]), "rejected")
    await message.answer("🚫 Відхилено.")


@router.message(Command("allapprove"))
async def cmd_all_approve(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        await message.answer("Немає відкритого циклу.")
        return
    cur = await db.conn.execute(
        "UPDATE order_requests SET status='approved', updated_at=datetime('now') "
        "WHERE cycle_id = ? AND status='pending'",
        (cycle.id,),
    )
    await db.conn.commit()
    await message.answer(f"✅ Підтверджено {cur.rowcount} позицій.")


@router.message(Command("catalog"))
async def cmd_catalog(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    parts = shlex.split(message.text or "")
    if len(parts) < 2:
        items = await catalog.list_items(db, limit=50)
        if not items:
            await message.answer(
                "Каталог порожній.\n"
                "Додати: `/catalog add \"Назва\" одиниця кількість \"Постачальник\"`",
                parse_mode="Markdown",
            )
            return
        lines = [f"*Каталог* ({len(items)})", ""]
        for it in items:
            sup = f" — {it.supplier}" if it.supplier else ""
            lines.append(f"#{it.id} {it.name} ({it.unit}){sup}")
        lines += [
            "",
            "Додати: `/catalog add \"Назва\" од к-сть \"Постач.\"`",
            "Видалити: `/catalog del <id>`",
        ]
        await message.answer("\n".join(lines), parse_mode="Markdown")
        return

    sub = parts[1]
    if sub == "add":
        if len(parts) < 5:
            await message.answer(
                "Формат: `/catalog add \"Назва\" одиниця кількість [\"Постачальник\"]`",
                parse_mode="Markdown",
            )
            return
        name = parts[2]
        unit = parts[3]
        try:
            qty = float(parts[4].replace(",", "."))
        except ValueError:
            await message.answer("Кількість має бути числом.")
            return
        supplier = parts[5] if len(parts) >= 6 else None
        item_id = await catalog.add_item(db, name, unit, qty, supplier)
        await message.answer(f"✅ Додано #{item_id} «{name}»")
    elif sub == "del" and len(parts) >= 3 and parts[2].isdigit():
        await catalog.archive_item(db, int(parts[2]))
        await message.answer("🗄 Архівовано.")
    else:
        await message.answer("Невідома підкоманда. Спробуйте `/catalog`.")


@router.message(Command("users"))
async def cmd_users(message: types.Message, user: User, db: Database):
    if not _is_admin(user):
        return
    parts = shlex.split(message.text or "")
    if len(parts) < 2:
        cur = await db.conn.execute(
            "SELECT tg_id, full_name, role, default_cabinet_id FROM users ORDER BY role, id"
        )
        rows = await cur.fetchall()
        if not rows:
            await message.answer("Користувачів немає.")
            return
        lines = ["*Користувачі*", ""]
        for r in rows:
            cab = f" cab#{r['default_cabinet_id']}" if r["default_cabinet_id"] else ""
            lines.append(f"`{r['tg_id']}` — {r['full_name']} ({r['role']}){cab}")
        lines += [
            "",
            "Додати: `/users add <tg_id> <role> [cabinet] \"Імʼя\"`",
            "Видалити: `/users del <tg_id>`",
            "Ролі: assistant | admin | owner",
        ]
        await message.answer("\n".join(lines), parse_mode="Markdown")
        return

    sub = parts[1]
    if sub == "add":
        if len(parts) < 4:
            await message.answer(
                "Формат: `/users add <tg_id> <role> [cabinet] \"Імʼя\"`",
                parse_mode="Markdown",
            )
            return
        try:
            tg_id = int(parts[2])
        except ValueError:
            await message.answer("tg_id має бути числом.")
            return
        role = parts[3]
        if role not in ("assistant", "admin", "owner"):
            await message.answer("Ролі: assistant | admin | owner.")
            return
        cabinet = None
        name_idx = 4
        if len(parts) > 4 and parts[4].isdigit():
            cabinet = int(parts[4])
            name_idx = 5
        full_name = parts[name_idx] if len(parts) > name_idx else f"User {tg_id}"

        try:
            await db.conn.execute(
                "INSERT INTO users (tg_id, full_name, role, default_cabinet_id) "
                "VALUES (?, ?, ?, ?)",
                (tg_id, full_name, role, cabinet),
            )
            await db.conn.commit()
            await message.answer(f"✅ Додано {full_name} ({role}).")
        except Exception as e:
            await message.answer(f"❌ {e}")
    elif sub == "del" and len(parts) >= 3:
        try:
            tg_id = int(parts[2])
        except ValueError:
            await message.answer("tg_id має бути числом.")
            return
        await db.conn.execute("DELETE FROM users WHERE tg_id = ?", (tg_id,))
        await db.conn.commit()
        await message.answer("🗑 Видалено.")
    else:
        await message.answer("Невідома підкоманда. Спробуйте `/users`.")
