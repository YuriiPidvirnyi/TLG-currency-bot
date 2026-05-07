from aiogram import Router, types
from aiogram.filters import Command, CommandStart

from app.models import User

router = Router()


HELP_BY_ROLE = {
    "assistant": (
        "Ви — *асистент*.\n\n"
        "/add — додати позицію в поточне замовлення\n"
        "/my — мої позиції в поточному циклі\n"
        "/cabinet — змінити дефолтний кабінет"
    ),
    "admin": (
        "Ви — *адміністратор*.\n\n"
        "/add /my /cabinet — як в асистента\n"
        "/open — відкрити новий цикл\n"
        "/close — закрити цикл і сформувати звіт\n"
        "/pending — позиції на ревʼю (free-form)\n"
        "/preview — попередній перегляд звіту без закриття\n"
        "/catalog — керувати каталогом\n"
        "/users — керувати користувачами\n"
        "/cycle — статус поточного циклу"
    ),
    "owner": (
        "Ви — *власниця клініки*.\n\n"
        "/report — попередній перегляд поточного циклу\n"
        "/history — попередні звіти"
    ),
}


@router.message(CommandStart())
async def cmd_start(message: types.Message, user: User | None):
    if not user:
        return  # auth middleware already replied
    text = (
        f"Вітаю, {user.full_name}! 👋\n\n"
        + HELP_BY_ROLE.get(user.role, "Невідома роль.")
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: types.Message, user: User | None):
    if not user:
        return
    await message.answer(HELP_BY_ROLE.get(user.role, ""), parse_mode="Markdown")


@router.message(Command("whoami"))
async def cmd_whoami(message: types.Message, user: User | None):
    if not user:
        return
    await message.answer(
        f"ID: `{user.tg_id}`\nІмʼя: {user.full_name}\nРоль: {user.role}\n"
        f"Кабінет за замовч.: {user.default_cabinet_id or '—'}",
        parse_mode="Markdown",
    )
