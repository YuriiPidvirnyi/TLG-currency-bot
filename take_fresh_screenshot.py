"""Build the rates archive PNG from PrivatBank's public exchange-rate API.

- /pubinfo?coursid=11 (cash, fallback 5) gives the current live rate.
- /exchange_rates?date=DD.MM.YYYY gives end-of-day rates for history.
"""
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

OUTPUT_PATH = "/app/privatbank_rates.png"
ARCHIVE_URL = "https://api.privatbank.ua/p24api/exchange_rates"
PUBINFO_URL = "https://api.privatbank.ua/p24api/pubinfo"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DAYS = 14
CURRENCIES = ("USD", "EUR")
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _step(n: int, total: int, desc: str) -> None:
    print(f"STEP:{n}:{total}:{desc}", flush=True)


def _get_json(url: str, attempts: int = 4, backoff: float = 1.5) -> object:
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


def _fetch_current() -> dict:
    """Live rates. Try cash (coursid=11), fall back to non-cash (coursid=5)."""
    for cid in (11, 5):
        try:
            data = _get_json(f"{PUBINFO_URL}?json&exchange&coursid={cid}", attempts=2)
            if isinstance(data, list) and data:
                rates = {}
                for item in data:
                    cur = item.get("ccy")
                    if cur in CURRENCIES:
                        rates[cur] = {"buy": float(item["buy"]), "sell": float(item["sale"])}
                if rates:
                    return rates
        except Exception as e:
            print(f"  warn: pubinfo coursid={cid}: {e}", flush=True)
    return {}


def _fetch_archive() -> list:
    today = datetime.now().date()
    rows = []
    for i in range(DAYS):
        d = today - timedelta(days=i)
        ds = d.strftime("%d.%m.%Y")
        qs = urllib.parse.urlencode({"json": "", "date": ds})
        try:
            data = _get_json(f"{ARCHIVE_URL}?{qs}")
        except Exception as e:
            print(f"  warn: archive {ds}: {e}", flush=True)
            continue
        for cur in CURRENCIES:
            for rate in data.get("exchangeRate", []):
                if rate.get("currency") == cur and "saleRate" in rate:
                    rows.append({
                        "date": ds,
                        "currency": f"UAH/{cur}",
                        "buy": float(rate["purchaseRate"]),
                        "sell": float(rate["saleRate"]),
                    })
                    break
    return rows


def _font(size: int):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render(current: dict, archive: list, output_path: str) -> None:
    if not current and not archive:
        raise RuntimeError("API повернуло порожньо — нема даних для відображення")

    title_font = _font(24)
    head_font = _font(18)
    cell_font = _font(16)
    sub_font = _font(13)
    section_font = _font(17)

    cols = [("Дата / Час", 160), ("Валюта", 110), ("Купівля", 130), ("Продаж", 130)]
    pad = 20
    width = pad * 2 + sum(w for _, w in cols)
    title_h = 40
    sub_h = 22
    section_h = 32
    head_h = 50
    row_h = 40
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    current_rows = len(current)
    archive_rows = len(archive)
    height = (
        pad + title_h + sub_h + 12
        + (section_h + row_h * current_rows + 12 if current_rows else 0)
        + section_h + head_h + row_h * archive_rows
        + pad
    )

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    d.text((pad, pad), "Курси валют Приватбанку", fill="black", font=title_font)
    d.text((pad, pad + title_h), f"Згенеровано {now_str}", fill="#666", font=sub_font)

    y = pad + title_h + sub_h + 12

    if current_rows:
        d.rectangle([(pad, y), (width - pad, y + section_h)], fill="#e7f3ff")
        d.text((pad + 12, y + 7), f"Поточний курс • {now_str}",
               fill="#0a5cff", font=section_font)
        y += section_h
        for i, cur in enumerate(CURRENCIES):
            if cur not in current:
                continue
            r = current[cur]
            if i % 2 == 0:
                d.rectangle([(pad, y), (width - pad, y + row_h)], fill="#f7fbff")
            x = pad + 12
            cells = [now_str, f"UAH/{cur}", f"{r['buy']:.4f}", f"{r['sell']:.4f}"]
            for val, (_, w) in zip(cells, cols):
                d.text((x, y + 11), val, fill="#0a2540", font=cell_font)
                x += w
            d.line([(pad, y + row_h), (width - pad, y + row_h)], fill="#d6e8ff", width=1)
            y += row_h
        y += 12

    d.rectangle([(pad, y), (width - pad, y + section_h)], fill="#f0f3f7")
    d.text((pad + 12, y + 7), f"Архів за останні {DAYS} днів",
           fill="#1f2d3d", font=section_font)
    y += section_h

    d.rectangle([(pad, y), (width - pad, y + head_h)], fill="#fafbfc")
    x = pad + 12
    for name, w in cols:
        d.text((x, y + 14), name, fill="#1f2d3d", font=head_font)
        x += w
    d.line([(pad, y + head_h), (width - pad, y + head_h)], fill="#cbd5e0", width=1)
    y += head_h

    for i, row in enumerate(archive):
        if i % 2 == 0:
            d.rectangle([(pad, y), (width - pad, y + row_h)], fill="#fafbfc")
        x = pad + 12
        cells = [row["date"], row["currency"], f"{row['buy']:.4f}", f"{row['sell']:.4f}"]
        for val, (_, w) in zip(cells, cols):
            d.text((x, y + 11), val, fill="#222", font=cell_font)
            x += w
        d.line([(pad, y + row_h), (width - pad, y + row_h)], fill="#eef2f7", width=1)
        y += row_h

    d.rectangle([(0, 0), (width - 1, height - 1)], outline="#cbd5e0", width=1)
    img.save(output_path)


def main():
    _step(1, 4, "Тягну поточний курс")
    current = _fetch_current()

    _step(2, 4, f"Тягну архів за {DAYS} днів")
    archive = _fetch_archive()

    _step(3, 4, f"Малюю таблицю ({len(current)} live + {len(archive)} архів)")
    _render(current, archive, OUTPUT_PATH)

    _step(4, 4, "Зберігаю PNG")
    print(f"DONE:{OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
