import asyncio
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_CHAT_ID = int(os.environ.get("ALLOWED_CHAT_ID") or "0")
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID") or "0")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ARCHIVE_URL = "https://api.privatbank.ua/p24api/exchange_rates"
PUBINFO_URL = "https://api.privatbank.ua/p24api/pubinfo"
HISTORY_DAYS = 30
CURRENCY = "USD"


def _is_authorized(message: types.Message) -> bool:
    return message.chat.id in (ALLOWED_CHAT_ID, OWNER_CHAT_ID)


def _get_json(url: str, attempts: int = 3, backoff: float = 1.0) -> object:
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
                last = f"HTTP {resp.status}"
        except Exception as e:
            last = str(e)
        time.sleep(backoff * (i + 1))
    raise RuntimeError(last or "unknown error")


def _fetch_live() -> dict:
    """Returns {'безготівка': (buy, sell), 'готівка': (buy, sell)} for USD."""
    out = {}
    for cid, label in ((5, "безготівка"), (11, "готівка")):
        try:
            data = _get_json(f"{PUBINFO_URL}?json&exchange&coursid={cid}", attempts=2)
        except Exception as e:
            logging.warning("pubinfo coursid=%s: %s", cid, e)
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if item.get("ccy") == CURRENCY:
                out[label] = (float(item["buy"]), float(item["sale"]))
                break
    return out


def _fetch_history(days: int) -> list:
    today = datetime.now().date()
    rows = []
    for i in range(days):
        d = today - timedelta(days=i)
        ds = d.strftime("%d.%m.%Y")
        qs = urllib.parse.urlencode({"json": "", "date": ds})
        try:
            data = _get_json(f"{ARCHIVE_URL}?{qs}")
        except Exception as e:
            logging.warning("archive %s: %s", ds, e)
            continue
        for rate in data.get("exchangeRate", []):
            if rate.get("currency") == CURRENCY and "saleRate" in rate:
                rows.append((ds, float(rate["purchaseRate"]), float(rate["saleRate"])))
                break
    return rows


def _format_live(live: dict) -> str:
    if not live:
        return "❌ Не вдалось отримати поточний курс. Спробуй пізніше."
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    lines = [f"💵 *{CURRENCY}/UAH • поточний курс*", f"_{ts}_", ""]
    for label, (buy, sell) in live.items():
        lines.append(f"*{label.capitalize()}:*  `{buy:.4f}` / `{sell:.4f}`")
    lines.append("")
    lines.append("_Купівля / Продаж_")
    return "\n".join(lines)


def _format_history(rows: list) -> str:
    if not rows:
        return "❌ Архів порожній. Спробуй пізніше."
    lines = [f"📊 *{CURRENCY}/UAH • архів за {len(rows)} днів*", ""]
    lines.append("```")
    lines.append(f"{'Дата':<11} {'Купівля':>9}  {'Продаж':>9}")
    lines.append("─" * 32)
    for date, buy, sell in rows:
        lines.append(f"{date:<11} {buy:>9.4f}  {sell:>9.4f}")
    lines.append("```")
    lines.append("_Закриваючий курс банку за день (безготівковий)_")
    return "\n".join(lines)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not _is_authorized(message):
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return
    await message.answer(
        "Привіт! 👋\n\n"
        f"Курси *{CURRENCY}* від Приватбанку.\n\n"
        "Команди:\n"
        "/now — поточний курс (готівка + безготівка)\n"
        f"/history — архів за {HISTORY_DAYS} днів\n"
        "/rates — поточний + архів одним повідомленням\n"
        "/start — це повідомлення"
    )


@dp.message(Command("now"))
async def cmd_now(message: types.Message):
    if not _is_authorized(message):
        return
    wait = await message.answer("⏳ Запитую курс...")
    try:
        live = await asyncio.to_thread(_fetch_live)
        await wait.edit_text(_format_live(live))
    except Exception as e:
        logging.exception("cmd_now failed")
        await wait.edit_text(f"❌ Помилка: `{str(e)[:200]}`")


@dp.message(Command("history"))
async def cmd_history(message: types.Message):
    if not _is_authorized(message):
        return
    wait = await message.answer(f"⏳ Збираю архів за {HISTORY_DAYS} днів...")
    try:
        rows = await asyncio.to_thread(_fetch_history, HISTORY_DAYS)
        await wait.edit_text(_format_history(rows))
    except Exception as e:
        logging.exception("cmd_history failed")
        await wait.edit_text(f"❌ Помилка: `{str(e)[:200]}`")


@dp.message(Command("rates"))
async def cmd_rates(message: types.Message):
    if not _is_authorized(message):
        return
    wait = await message.answer("⏳ Збираю курс і архів...")
    try:
        live, rows = await asyncio.gather(
            asyncio.to_thread(_fetch_live),
            asyncio.to_thread(_fetch_history, HISTORY_DAYS),
        )
        text = _format_live(live) + "\n\n" + _format_history(rows)
        await wait.edit_text(text)
    except Exception as e:
        logging.exception("cmd_rates failed")
        await wait.edit_text(f"❌ Помилка: `{str(e)[:200]}`")


async def main():
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
