import asyncio
import contextlib
import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID") or "0")
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID") or "0")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SCREENSHOT_PATH = "/app/privatbank_rates.png"
SCREENSHOT_SCRIPT = "/app/take_fresh_screenshot.py"


def _progress_bar(step: int, total: int, desc: str) -> str:
    filled = round(step / total * 10)
    bar = "█" * filled + "░" * (10 - filled)
    pct = round(step / total * 100)
    return f"🔄 Оновлюю курси...\n\n{bar}  {pct}%\n📍 {desc}"


async def _run_screenshot(progress_cb=None) -> None:
    proc = await asyncio.create_subprocess_exec(
        "python3", SCREENSHOT_SCRIPT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def _read_stdout():
        async for raw in proc.stdout:
            text = raw.decode().strip()
            if progress_cb and text.startswith("STEP:"):
                parts = text.split(":", 3)
                if len(parts) == 4:
                    with contextlib.suppress(Exception):
                        await progress_cb(int(parts[1]), int(parts[2]), parts[3])

    try:
        _, stderr_bytes = await asyncio.wait_for(
            asyncio.gather(_read_stdout(), proc.stderr.read()),
            timeout=120,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise

    await proc.wait()
    if proc.returncode != 0:
        err = stderr_bytes.decode().strip()
        # Show last 5 lines — that's where the actual exception type/message lives
        last = "\n".join(err.splitlines()[-5:])
        raise Exception(last)


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
        "/refresh — свіжий скрін просто зараз 🔄 (~10 сек)\n"
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
        caption=f"Архів курсів валют Приватбанку 📊\n🕐 Оновлено: {updated}",
    )


@dp.message(Command("refresh"))
async def cmd_refresh(message: types.Message):
    if message.chat.id not in [ALLOWED_CHAT_ID, OWNER_CHAT_ID]:
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return

    wait_msg = await message.answer(
        "🔄 Оновлюю курси...\n\n░░░░░░░░░░  0%\n📍 Запускаю..."
    )

    async def on_progress(step: int, total: int, desc: str) -> None:
        with contextlib.suppress(Exception):
            await wait_msg.edit_text(_progress_bar(step, total, desc))

    try:
        await _run_screenshot(progress_cb=on_progress)
        await bot.delete_message(message.chat.id, wait_msg.message_id)
        mtime_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        await message.answer_photo(
            types.FSInputFile(SCREENSHOT_PATH),
            caption=f"Курси валют Приватбанку 📊 (архів)\n🔄 Щойно оновлено: {mtime_str}",
        )
    except asyncio.TimeoutError:
        await wait_msg.edit_text("❌ Час очікування вичерпано (>2 хв). Спробуй ще раз.")
    except Exception as e:
        logging.error("Refresh error: %s", e, exc_info=True)
        await wait_msg.edit_text(f"❌ Помилка:\n{str(e)[:300]}")


async def _startup_screenshot():
    try:
        await _run_screenshot()
        logging.info("Startup screenshot ready")
    except Exception as e:
        logging.error("Startup screenshot failed: %s", e, exc_info=True)


async def scheduled_update():
    logging.info("Scheduled screenshot update started")
    try:
        await _run_screenshot()
        mtime_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        caption = f"Курси валют Приватбанку 📊 (архів)\n🕐 Автооновлення: {mtime_str}"
        for chat_id in {ALLOWED_CHAT_ID, OWNER_CHAT_ID}:
            if chat_id:
                with contextlib.suppress(Exception):
                    await bot.send_photo(
                        chat_id, types.FSInputFile(SCREENSHOT_PATH), caption=caption
                    )
    except Exception as e:
        logging.error("Scheduled update error: %s", e, exc_info=True)


async def main():
    asyncio.create_task(_startup_screenshot())

    try:
        scheduler = AsyncIOScheduler()
        for hour in [6, 12, 15, 18, 21, 0]:
            scheduler.add_job(scheduled_update, "cron", hour=hour, minute=0)
        scheduler.start()
        logging.info("Scheduler started successfully")
    except Exception as e:
        logging.error("Scheduler failed to start: %s", e, exc_info=True)

    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
