import asyncio
import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", "0"))
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID", "0"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SCREENSHOT_PATH = "/app/privatbank_rates.png"
SCREENSHOT_SCRIPT = "/app/take_fresh_screenshot.py"


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.id not in [ALLOWED_CHAT_ID, OWNER_CHAT_ID]:
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return
    await message.answer(
        "Привіт! 👋\n\n"
        "Надсилаю архів курсів валют Приватбанку.\n\n"
        "Команди:\n"
        "/rates — останній збережений скрін 📊\n"
        "/refresh — свіжий скрін просто зараз 🔄 (~1-2 хв)\n"
        "/start — це повідомлення\n\n"
        "🕐 Автооновлення: 06:00, 12:00, 15:00, 18:00, 21:00, 00:00"
    )


@dp.message(Command("rates"))
async def cmd_rates(message: types.Message):
    if message.chat.id not in [ALLOWED_CHAT_ID, OWNER_CHAT_ID]:
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return

    if not os.path.exists(SCREENSHOT_PATH):
        await message.answer("⚠️ Скрін ще не готовий. Спробуй пізніше.")
        return

    mtime = os.path.getmtime(SCREENSHOT_PATH)
    updated = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")

    await message.answer_photo(
        types.FSInputFile(SCREENSHOT_PATH),
        caption=f"Архів курсів валют Приватбанку 📊\n🕐 Оновлено: {updated}"
    )


async def _run_screenshot() -> None:
    proc = await asyncio.create_subprocess_exec(
        "python3", SCREENSHOT_SCRIPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    if proc.returncode != 0:
        raise Exception(stderr.decode()[:300])


@dp.message(Command("refresh"))
async def cmd_refresh(message: types.Message):
    if message.chat.id not in [ALLOWED_CHAT_ID, OWNER_CHAT_ID]:
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return

    wait_msg = await message.answer("⏳ Роблю свіжий скрін... Зачекай ~1-2 хв.")

    try:
        await _run_screenshot()
        await bot.delete_message(message.chat.id, wait_msg.message_id)
        mtime_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        await message.answer_photo(
            types.FSInputFile(SCREENSHOT_PATH),
            caption=f"Курси валют Приватбанку 📊 (архів)\n🔄 Щойно оновлено: {mtime_str}"
        )
    except asyncio.TimeoutError:
        await wait_msg.edit_text("❌ Час очікування вичерпано. Спробуй ще раз.")
    except Exception as e:
        logging.error(f"Refresh error: {e}", exc_info=True)
        await wait_msg.edit_text(f"❌ Помилка: {str(e)[:200]}")


async def scheduled_update():
    logging.info("Scheduled screenshot update started")
    try:
        await _run_screenshot()
        mtime_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        caption = f"Курси валют Приватбанку 📊 (архів)\n🕐 Автооновлення: {mtime_str}"
        for chat_id in {ALLOWED_CHAT_ID, OWNER_CHAT_ID}:
            if chat_id:
                try:
                    await bot.send_photo(chat_id, types.FSInputFile(SCREENSHOT_PATH), caption=caption)
                except Exception as e:
                    logging.error(f"Failed to send scheduled update to {chat_id}: {e}")
    except Exception as e:
        logging.error(f"Scheduled update error: {e}", exc_info=True)


async def main():
    scheduler = AsyncIOScheduler()
    for hour in [6, 12, 15, 18, 21, 0]:
        scheduler.add_job(scheduled_update, "cron", hour=hour, minute=0)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
