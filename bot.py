import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID", "0"))  # Marta's chat_id

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def take_privatbank_screenshot() -> str:
    """Відкриває архів курсів Приватбанку і робить скріншот таблиці."""
    path = "/tmp/privatbank_rates.png"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto("https://privatbank.ua/obmin-valiut", wait_until="networkidle")

        # Клікаємо "Архів"
        await page.get_by_text("Архів", exact=False).first.click()
        await page.wait_for_timeout(2000)

        # Клікаємо "Таблиця"
        try:
            await page.get_by_text("Таблиця", exact=False).first.click()
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        # Завантажуємо всі дані
        while True:
            try:
                btn = page.get_by_text("Завантажити ще", exact=False).first
                if await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1500)
                else:
                    break
            except Exception:
                break

        # Скріншот таблиці
        await page.wait_for_timeout(1000)
        await page.screenshot(path=path, full_page=True)
        await browser.close()
    return path


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if ALLOWED_CHAT_ID and message.chat.id != ALLOWED_CHAT_ID:
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return
    await message.answer(
        "Привіт! 👋\n\n"
        "Я надсилаю актуальні курси валют Приватбанку.\n\n"
        "Команди:\n"
        "/курси — отримати скрін курсів валют\n"
        "/start — це повідомлення"
    )


@dp.message(Command("курси"))
async def cmd_rates(message: types.Message):
    if ALLOWED_CHAT_ID and message.chat.id != ALLOWED_CHAT_ID:
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return
    wait_msg = await message.answer("⏳ Отримую курси валют, зачекай хвилинку...")
    try:
        path = await take_privatbank_screenshot()
        await bot.delete_message(message.chat.id, wait_msg.message_id)
        await message.answer_photo(
            types.FSInputFile(path),
            caption="Курси валют Приватбанку (архів) 📊"
        )
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("Помилка при отриманні курсів. Спробуй ще раз.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
