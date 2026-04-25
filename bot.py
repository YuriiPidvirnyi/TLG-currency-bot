import asyncio
import io
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
from aiogram.types import BotCommand, BufferedInputFile
from PIL import Image, ImageDraw, ImageFont

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
            date, t, cur, buy, sell = tds
            try:
                buy_f = float(buy.replace(",", "."))
                sell_f = float(sell.replace(",", "."))
            except ValueError:
                continue
            rows.append((date, t, cur, buy_f, sell_f))
    rows.reverse()  # newest first
    return rows


_FONT_REG = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
_FONT_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for p in (_FONT_BOLD if bold else _FONT_REG):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_archive_png(rows: list, subtitle: str, currency: str) -> bytes:
    PB_GREEN = "#0ba373"
    HEADER_BG = "#f4f5f7"
    BORDER = "#e1e4e8"
    ROW_ALT = "#fafbfc"
    TEXT = "#1f2d3d"
    SUBTLE = "#6a7280"
    BUY = "#1e7e34"
    SELL = "#c0392b"

    title_font = _font(28, bold=True)
    subtitle_font = _font(14)
    head_font = _font(16, bold=True)
    cell_font = _font(16)
    cell_bold = _font(16, bold=True)

    cols = [("Дата", 150), ("Час", 110), ("Купівля", 130), ("Продаж", 130)]
    pad = 24
    width = pad * 2 + sum(w for _, w in cols)
    title_h, sub_h, head_h, row_h = 44, 24, 50, 42
    height = pad + title_h + sub_h + 16 + head_h + row_h * len(rows) + pad

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    d.rectangle([(0, 0), (width, 6)], fill=PB_GREEN)
    d.text((pad, pad), f"{currency}/UAH • Архів", fill=TEXT, font=title_font)
    d.text((pad, pad + title_h), subtitle, fill=SUBTLE, font=subtitle_font)

    y = pad + title_h + sub_h + 16
    d.rectangle([(pad, y), (width - pad, y + head_h)], fill=HEADER_BG)
    x = pad + 12
    for name, w in cols:
        d.text((x, y + 16), name, fill=TEXT, font=head_font)
        x += w
    d.line([(pad, y + head_h), (width - pad, y + head_h)], fill=BORDER, width=1)
    y += head_h

    for i, (date, t, _cur, buy, sell) in enumerate(rows):
        if i % 2 == 0:
            d.rectangle([(pad, y), (width - pad, y + row_h)], fill=ROW_ALT)
        x = pad + 12
        cells = [
            (date, TEXT, cell_font),
            (t, SUBTLE, cell_font),
            (f"{buy:.4f}", BUY, cell_bold),
            (f"{sell:.4f}", SELL, cell_bold),
        ]
        for (val, color, font), (_, w) in zip(cells, cols):
            d.text((x, y + 12), val, fill=color, font=font)
            x += w
        d.line([(pad, y + row_h), (width - pad, y + row_h)], fill=BORDER, width=1)
        y += row_h

    d.rectangle([(0, 0), (width - 1, height - 1)], outline=BORDER, width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not _is_authorized(message):
        await message.answer("Вибач, цей бот лише для особистого використання.")
        return
    await message.answer(
        "Привіт! 👋\n\n"
        f"Архів готівкового курсу *{DEFAULT_CURRENCY}* від Приватбанку:\n\n"
        "/today — всі сьогоднішні зміни курсу\n"
        "/week — за останній тиждень\n"
        "/month — за останній місяць\n"
        "/year — за рік (макс. 60 останніх записів)\n\n"
        "/start — це повідомлення"
    )


async def _reply_archive(message: types.Message, period: str, today_only: bool = False):
    if not _is_authorized(message):
        return
    label = "за сьогодні" if today_only else PERIOD_LABELS[period]
    wait = await message.answer(f"⏳ Тягну архів {label}...")
    try:
        rows = await asyncio.to_thread(_fetch_archive, period)
        if today_only:
            today = datetime.now().strftime("%d-%m-%Y")
            rows = [r for r in rows if r[0] == today]
        if not rows:
            await wait.edit_text(f"❌ Архів порожній ({label}).")
            return
        cropped = rows[:MAX_TG_ROWS]
        ts = datetime.now().strftime("%d.%m.%Y %H:%M")
        suffix = f" (показано перші {len(cropped)})" if len(rows) > len(cropped) else ""
        subtitle = f"{label} • згенеровано {ts} • {len(rows)} записів{suffix}"
        png = await asyncio.to_thread(_render_archive_png, cropped, subtitle, DEFAULT_CURRENCY)
        await bot.delete_message(message.chat.id, wait.message_id)
        await message.answer_photo(
            BufferedInputFile(png, filename=f"rates_{period}.png"),
            caption=f"📊 *Архів {DEFAULT_CURRENCY}/UAH • {label}*",
        )
    except Exception as e:
        logging.exception("archive %s failed", period)
        await wait.edit_text(f"❌ Помилка: `{str(e)[:200]}`")


@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    # Pull from week so all intra-day records show, then filter to today
    await _reply_archive(message, "week", today_only=True)


@dp.message(Command("week"))
async def cmd_week(message: types.Message):
    await _reply_archive(message, "week")


@dp.message(Command("month"))
async def cmd_month(message: types.Message):
    await _reply_archive(message, "month")


@dp.message(Command("year"))
async def cmd_year(message: types.Message):
    await _reply_archive(message, "year")


async def _set_commands_menu():
    await bot.set_my_commands([
        BotCommand(command="today", description="Зміни курсу за сьогодні"),
        BotCommand(command="week", description="Архів за тиждень"),
        BotCommand(command="month", description="Архів за місяць"),
        BotCommand(command="year", description="Архів за рік"),
        BotCommand(command="start", description="Список команд"),
    ])


async def main():
    await _set_commands_menu()
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
