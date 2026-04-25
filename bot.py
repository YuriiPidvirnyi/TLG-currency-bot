import asyncio
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html import unescape

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
ARCHIVE_ENDPOINT = "https://privatbank.ua/rates/get-archive"
PUBINFO_URL = "https://api.privatbank.ua/p24api/pubinfo"
DEFAULT_CURRENCY = "USD"
PERIOD_LABELS = {
    "day": "за день",
    "week": "за тиждень",
    "month": "за місяць",
    "year": "за рік",
}
MAX_TG_ROWS = 60  # crop to fit one Telegram message


def _is_authorized(message: types.Message) -> bool:
    return message.chat.id in (ALLOWED_CHAT_ID, OWNER_CHAT_ID)


def _http_get(url: str, headers: dict | None = None, attempts: int = 3) -> str:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    return resp.read().decode()
                last = f"HTTP {resp.status}"
        except Exception as e:
            last = str(e)
        time.sleep(1.0 * (i + 1))
    raise RuntimeError(last or "unknown error")


def _fetch_live(currency: str = DEFAULT_CURRENCY) -> dict:
    out = {}
    for cid, label in ((5, "безготівка"), (11, "готівка")):
        try:
            text = _http_get(f"{PUBINFO_URL}?json&exchange&coursid={cid}", attempts=2)
            data = json.loads(text)
        except Exception as e:
            logging.warning("pubinfo coursid=%s: %s", cid, e)
            continue
        for item in data:
            if item.get("ccy") == currency:
                out[label] = (float(item["buy"]), float(item["sale"]))
                break
    return out


_TR_RE = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _fetch_archive(period: str, currency: str = DEFAULT_CURRENCY) -> list:
    """Returns list of (date, time, currency, buy, sell) — same format as
    privatbank.ua/obmin-valiut Архів table. Newest first."""
    qs = urllib.parse.urlencode({
        "period": period,
        "from_currency": "UAH",
        "to_currency": currency,
        "table-view": "1",
        "all": "1",
    })
    raw = _http_get(
        f"{ARCHIVE_ENDPOINT}?{qs}",
        headers={"Referer": "https://privatbank.ua/obmin-valiut", "Accept": "application/json"},
    )
    data = json.loads(raw)
    html = data.get("content", "")
    rows = []
    for tr in _TR_RE.findall(html):
        tds = [_TAG_RE.sub("", unescape(td)).strip() for td in _TD_RE.findall(tr)]
        if len(tds) == 5:
            rows.append(tuple(tds))
    rows.reverse()  # newest first
    return rows


def _format_live(live: dict, currency: str) -> str:
    if not live:
        return "❌ Не вдалось отримати поточний курс."
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    lines = [f"💵 *{currency}/UAH • поточний курс*", f"_{ts}_", ""]
    for label, (buy, sell) in live.items():
        lines.append(f"*{label.capitalize()}:*  `{buy:.4f}` / `{sell:.4f}`")
    lines.append("")
    lines.append("_Купівля / Продаж_")
    return "\n".join(lines)


def _format_archive(rows: list, period: str, currency: str) -> str:
    if not rows:
        return f"❌ Архів порожній для періоду {PERIOD_LABELS.get(period, period)}."
    total = len(rows)
    cropped = rows[:MAX_TG_ROWS]
    lines = [
        f"📊 *Архів {currency}/UAH • {PERIOD_LABELS.get(period, period)}*",
        f"_Записів: {total}{' (показано перші ' + str(len(cropped)) + ')' if total > len(cropped) else ''}_",
        "",
        "```",
        f"{'Дата':<11} {'Час':<8} {'Купівля':>9} {'Продаж':>13}",
        "─" * 45,
    ]
    for date, t, _cur, buy, sell in cropped:
        lines.append(f"{date:<11} {t:<8} {buy:>9} {sell:>13}")
    lines.append("```")
    return "\n".join(lines)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not _is_authorized(message):
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return
    await message.answer(
        "Привіт! 👋\n\n"
        f"Курси *{DEFAULT_CURRENCY}* від Приватбанку.\n\n"
        "Команди:\n"
        "/now — поточний курс (готівка + безготівка)\n"
        "/today — архів за день\n"
        "/week — архів за тиждень\n"
        "/month — архів за місяць\n"
        "/year — архів за рік (макс. 60 рядків)\n"
        "/start — це повідомлення"
    )


async def _reply_archive(message: types.Message, period: str):
    if not _is_authorized(message):
        return
    wait = await message.answer(f"⏳ Тягну архів {PERIOD_LABELS[period]}...")
    try:
        rows = await asyncio.to_thread(_fetch_archive, period)
        await wait.edit_text(_format_archive(rows, period, DEFAULT_CURRENCY))
    except Exception as e:
        logging.exception("archive %s failed", period)
        await wait.edit_text(f"❌ Помилка: `{str(e)[:200]}`")


@dp.message(Command("now"))
async def cmd_now(message: types.Message):
    if not _is_authorized(message):
        return
    wait = await message.answer("⏳ Запитую курс...")
    try:
        live = await asyncio.to_thread(_fetch_live)
        await wait.edit_text(_format_live(live, DEFAULT_CURRENCY))
    except Exception as e:
        logging.exception("cmd_now failed")
        await wait.edit_text(f"❌ Помилка: `{str(e)[:200]}`")


@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    await _reply_archive(message, "day")


@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    await _reply_archive(message, "week")


@dp.message(Command("month"))
async def cmd_month(message: types.Message):
    await _reply_archive(message, "month")


@dp.message(Command("year"))
async def cmd_year(message: types.Message):
    await _reply_archive(message, "year")


async def main():
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
