import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import load_config
from app.db import Database
from app.handlers import admin, assistant, owner, start
from app.middlewares.auth import AuthMiddleware
from app.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def _set_commands_menu(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="add", description="Додати позицію"),
        BotCommand(command="my", description="Мої позиції в циклі"),
        BotCommand(command="cabinet", description="Дефолтний кабінет"),
        BotCommand(command="cycle", description="Стан циклу"),
        BotCommand(command="pending", description="Pending на ревʼю (admin)"),
        BotCommand(command="open", description="Відкрити цикл (admin)"),
        BotCommand(command="close", description="Закрити цикл і сформувати звіт (admin)"),
        BotCommand(command="preview", description="Попередній звіт"),
        BotCommand(command="catalog", description="Каталог матеріалів (admin)"),
        BotCommand(command="users", description="Користувачі (admin)"),
        BotCommand(command="report", description="Звіт по поточному циклу (owner)"),
        BotCommand(command="history", description="Історія циклів"),
        BotCommand(command="help", description="Допомога"),
    ])


async def main() -> None:
    config = load_config()
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    db = Database(config.db_path)
    await db.connect()
    await db.apply_migrations(config.migrations_dir)
    await db.seed_initial_admin(config.admin_chat_id)
    await db.seed_owner(config.owner_chat_id)

    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["config"] = config

    auth = AuthMiddleware(db)
    dp.message.middleware(auth)
    dp.callback_query.middleware(auth)

    dp.include_router(start.router)
    dp.include_router(assistant.router)
    dp.include_router(admin.router)
    dp.include_router(owner.router)

    sched = setup_scheduler(bot, db, config)
    sched.start()
    log.info("Scheduler started: jobs=%s", [j.id for j in sched.get_jobs()])

    await _set_commands_menu(bot)

    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        sched.shutdown(wait=False)
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
