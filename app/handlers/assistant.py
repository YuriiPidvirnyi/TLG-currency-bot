import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.db import Database
from app.fsm.add_item import AddItem
from app.models import User
from app.services import catalog, cycles, requests as req_service

log = logging.getLogger(__name__)
router = Router()


SKIP_TOKEN = "—"


def _cabinet_keyboard(cabinets: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"cab:{cid}")] for cid, name in cabinets]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _items_keyboard(items) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{i.name} ({i.unit})", callback_data=f"itm:{i.id}")] for i in items]
    rows.append([InlineKeyboardButton(text="➕ Своя позиція", callback_data="itm:free")])
    rows.append([InlineKeyboardButton(text="🔍 Пошук", callback_data="itm:search")])
    rows.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="itm:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Зберегти", callback_data="cf:save"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data="cf:cancel"),
    ]])


@router.message(Command("cabinet"))
async def cmd_cabinet(message: types.Message, user: User, db: Database):
    cabs = await catalog.list_cabinets(db)
    await message.answer(
        "Оберіть кабінет за замовчуванням:",
        reply_markup=_cabinet_keyboard(cabs),
    )


@router.callback_query(F.data.startswith("cab:"), ~F.message.text.startswith("Додавання"))
async def set_default_cabinet(call: types.CallbackQuery, user: User, db: Database, state: FSMContext):
    if await state.get_state():
        return  # add-item flow handles its own cab: callbacks
    cab_id = int(call.data.removeprefix("cab:"))
    await db.conn.execute(
        "UPDATE users SET default_cabinet_id = ? WHERE id = ?", (cab_id, user.id)
    )
    await db.conn.commit()
    await call.message.edit_text(f"✅ Дефолтний кабінет встановлено: #{cab_id}")
    await call.answer()


@router.message(Command("add"))
async def cmd_add(message: types.Message, user: User, db: Database, state: FSMContext):
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        await message.answer("⛔️ Немає відкритого циклу. Зверніться до адміністратора.")
        return
    await state.clear()
    await state.update_data(cycle_id=cycle.id)

    if user.default_cabinet_id:
        await state.update_data(cabinet_id=user.default_cabinet_id)
        items = await catalog.list_items(db, limit=10)
        await state.set_state(AddItem.item)
        await message.answer(
            f"Додавання позиції до циклу #{cycle.id}.\nКабінет: #{user.default_cabinet_id}\n\n"
            "Оберіть позицію або «➕ Своя позиція»:",
            reply_markup=_items_keyboard(items),
        )
    else:
        cabs = await catalog.list_cabinets(db)
        await state.set_state(AddItem.cabinet)
        await message.answer(
            f"Додавання позиції до циклу #{cycle.id}.\nОберіть кабінет:",
            reply_markup=_cabinet_keyboard(cabs),
        )


@router.callback_query(AddItem.cabinet, F.data.startswith("cab:"))
async def fsm_pick_cabinet(call: types.CallbackQuery, db: Database, state: FSMContext):
    cab_id = int(call.data.removeprefix("cab:"))
    await state.update_data(cabinet_id=cab_id)
    items = await catalog.list_items(db, limit=10)
    await state.set_state(AddItem.item)
    await call.message.edit_text(
        f"Кабінет: #{cab_id}\nОберіть позицію або «➕ Своя позиція»:",
        reply_markup=_items_keyboard(items),
    )
    await call.answer()


@router.callback_query(AddItem.item, F.data == "itm:cancel")
async def fsm_cancel_pick(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Додавання скасовано.")
    await call.answer()


@router.callback_query(AddItem.item, F.data == "itm:free")
async def fsm_pick_freeform(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddItem.free_form_name)
    await call.message.edit_text("✏️ Введіть назву позиції:")
    await call.answer()


@router.callback_query(AddItem.item, F.data == "itm:search")
async def fsm_search(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(_search=True)
    await call.message.edit_text("🔍 Введіть пошуковий запит (частину назви):")
    await call.answer()


@router.message(AddItem.item)
async def fsm_search_query(message: types.Message, db: Database, state: FSMContext):
    data = await state.get_data()
    if not data.get("_search"):
        return
    items = await catalog.list_items(db, query=message.text or "", limit=10)
    await state.update_data(_search=False)
    if not items:
        await message.answer(
            "Нічого не знайдено. Спробуйте інший запит або додайте «своєю позицією».",
            reply_markup=_items_keyboard([]),
        )
        return
    await message.answer("Знайдено:", reply_markup=_items_keyboard(items))


@router.callback_query(AddItem.item, F.data.startswith("itm:"))
async def fsm_pick_catalog(call: types.CallbackQuery, db: Database, state: FSMContext):
    payload = call.data.removeprefix("itm:")
    if not payload.isdigit():
        return
    item = await catalog.get_item(db, int(payload))
    if not item:
        await call.answer("Позицію не знайдено.", show_alert=True)
        return
    await state.update_data(
        catalog_item_id=item.id, item_name=item.name, unit=item.unit,
        default_qty=item.default_qty,
    )
    await state.set_state(AddItem.qty)
    await call.message.edit_text(
        f"📦 *{item.name}*\nОдиниця: {item.unit}\n\n"
        f"Введіть кількість (за замовч. {item.default_qty:g}):",
        parse_mode="Markdown",
    )
    await call.answer()


@router.message(AddItem.free_form_name)
async def fsm_freeform_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Назва закоротка, повторіть:")
        return
    await state.update_data(free_form_name=name, item_name=name)
    await state.set_state(AddItem.unit)
    await message.answer("Введіть одиницю виміру (шт, уп, мл, …):")


@router.message(AddItem.unit)
async def fsm_unit(message: types.Message, state: FSMContext):
    unit = (message.text or "").strip()
    if not unit:
        await message.answer("Невалідна одиниця, повторіть:")
        return
    await state.update_data(unit=unit)
    await state.set_state(AddItem.qty)
    await message.answer("Введіть кількість:")


@router.message(AddItem.qty)
async def fsm_qty(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip().replace(",", ".")
    data = await state.get_data()
    try:
        qty = float(txt) if txt else float(data.get("default_qty", 1))
    except ValueError:
        await message.answer("Введіть число, наприклад `2` або `1.5`.")
        return
    if qty <= 0:
        await message.answer("Кількість має бути більше нуля.")
        return
    await state.update_data(qty=qty)
    await state.set_state(AddItem.doctor)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=SKIP_TOKEN)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await message.answer(f"Лікар (ім'я) або `{SKIP_TOKEN}` щоб пропустити:", reply_markup=kb)


@router.message(AddItem.doctor)
async def fsm_doctor(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()
    doctor = None if txt in ("", SKIP_TOKEN) else txt
    await state.update_data(doctor_name=doctor)
    await state.set_state(AddItem.comment)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=SKIP_TOKEN)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await message.answer(
        f"Коментар (терміновість, бренд тощо) або `{SKIP_TOKEN}`:",
        reply_markup=kb,
    )


@router.message(AddItem.comment)
async def fsm_comment(message: types.Message, state: FSMContext):
    txt = (message.text or "").strip()
    comment = None if txt in ("", SKIP_TOKEN) else txt
    await state.update_data(comment=comment)
    data = await state.get_data()

    summary = (
        f"📝 *Підтвердження*\n\n"
        f"Кабінет: #{data['cabinet_id']}\n"
        f"Позиція: {data.get('item_name')}\n"
        f"К-сть: {data['qty']:g} {data.get('unit', '')}\n"
        f"Лікар: {data.get('doctor_name') or '—'}\n"
        f"Коментар: {data.get('comment') or '—'}\n"
    )
    if data.get("free_form_name"):
        summary += "\n⚠️ Позиція не з каталогу — потребує підтвердження адміна."

    await state.set_state(AddItem.confirm)
    await message.answer(summary, parse_mode="Markdown",
                         reply_markup=ReplyKeyboardRemove())
    await message.answer("Зберегти?", reply_markup=_confirm_keyboard())


@router.callback_query(AddItem.confirm, F.data == "cf:cancel")
async def fsm_confirm_cancel(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Скасовано.")
    await call.answer()


@router.callback_query(AddItem.confirm, F.data == "cf:save")
async def fsm_confirm_save(
    call: types.CallbackQuery, user: User, db: Database, state: FSMContext
):
    data = await state.get_data()
    try:
        if data.get("free_form_name"):
            req_id = await req_service.create_freeform_request(
                db,
                cycle_id=data["cycle_id"], user_id=user.id,
                cabinet_id=data["cabinet_id"], name=data["free_form_name"],
                qty=data["qty"], unit=data.get("unit", "шт"),
                comment=data.get("comment"), doctor_name=data.get("doctor_name"),
            )
            tail = "потрапить на ревʼю адміну"
        else:
            req_id = await req_service.create_catalog_request(
                db,
                cycle_id=data["cycle_id"], user_id=user.id,
                cabinet_id=data["cabinet_id"],
                catalog_item_id=data["catalog_item_id"],
                qty=data["qty"], unit=data.get("unit", "шт"),
                comment=data.get("comment"), doctor_name=data.get("doctor_name"),
            )
            tail = "додано до замовлення"
        await call.message.edit_text(f"✅ Збережено #{req_id} — {tail}.")
    except Exception as e:
        log.exception("save request failed")
        await call.message.edit_text(f"❌ Помилка: {e}")
    finally:
        await state.clear()
        await call.answer()


@router.message(Command("my"))
async def cmd_my(message: types.Message, user: User, db: Database):
    cycle = await cycles.get_open_cycle(db)
    if not cycle:
        await message.answer("⛔️ Немає відкритого циклу.")
        return
    rows = await req_service.list_user_requests(db, user.id, cycle.id)
    if not rows:
        await message.answer("Ваших позицій у цьому циклі поки немає. /add")
        return
    lines = [f"*Ваші позиції — цикл #{cycle.id}*", ""]
    for r in rows:
        name = r["catalog_name"] or r["free_form_name"]
        status = {"approved": "✅", "pending": "⏳", "rejected": "🚫"}.get(r["status"], "")
        lines.append(
            f"#{r['id']} {status} {name} — {r['qty']:g} {r['unit']} ({r['cabinet_name']})"
        )
    lines.append("")
    lines.append("Видалити: /del <id>")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("del"))
async def cmd_del(message: types.Message, user: User, db: Database):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Формат: `/del <id>`", parse_mode="Markdown")
        return
    ok = await req_service.delete_request(db, int(parts[1]), user_id=user.id)
    await message.answer("✅ Видалено." if ok else "❌ Не знайдено або не ваша позиція.")
