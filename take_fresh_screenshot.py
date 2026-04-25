"""Build the rates archive PNG from PrivatBank's public exchange-rate API.

Live "Поточний курс" section shows both:
- Безготівка (coursid=5) — same number you see on privatbank.ua/obmin-valiut
- Готівка (coursid=11) — physical-branch cash exchange

Archive section shows daily closing rates from /exchange_rates.
Currently USD-only; expand CURRENCIES to add more.
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
DAYS = 30
CURRENCIES = ("USD",)
LIVE_SOURCES = (
    (5, "безготівка"),
    (11, "готівка"),
)
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


def _fetch_live() -> list:
    """Returns list of {kind, currency, buy, sell} for each (coursid, currency)."""
    rows = []
    for cid, label in LIVE_SOURCES:
        try:
            data = _get_json(f"{PUBINFO_URL}?json&exchange&coursid={cid}", attempts=3)
        except Exception as e:
            print(f"  warn: pubinfo coursid={cid}: {e}", flush=True)
            continue
        if not isinstance(data, list):
            continue
        for cur in CURRENCIES:
            for item in data:
                if item.get("ccy") == cur:
                    rows.append({
                        "kind": label,
                        "currency": cur,
                        "buy": float(item["buy"]),
                        "sell": float(item["sale"]),
                    })
                    break
    return rows


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
                        "currency": cur,
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


def _render(live: list, archive: list, output_path: str) -> None:
    if not live and not archive:
        raise RuntimeError("API повернуло порожньо — нема даних для відображення")

    title_font = _font(24)
    head_font = _font(18)
    cell_font = _font(16)
    sub_font = _font(13)
    section_font = _font(17)

    pad = 20
    cols_live = [("Тип", 150), ("Валюта", 90), ("Купівля", 130), ("Продаж", 150)]
    cols_arch = [("Дата", 150), ("Валюта", 90), ("Купівля", 130), ("Продаж", 150)]
    width = pad * 2 + sum(w for _, w in cols_live)
    title_h = 40
    sub_h = 22
    section_h = 32
    head_h = 50
    row_h = 40
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    height = (
        pad + title_h + sub_h + 12
        + (section_h + head_h + row_h * len(live) + 16 if live else 0)
        + (section_h + head_h + row_h * len(archive) if archive else 0)
        + pad
    )

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    d.text((pad, pad), "Курси валют Приватбанку", fill="black", font=title_font)
    d.text((pad, pad + title_h), f"Згенеровано {now_str}", fill="#666", font=sub_font)

    y = pad + title_h + sub_h + 12

    if live:
        d.rectangle([(pad, y), (width - pad, y + section_h)], fill="#e7f3ff")
        d.text((pad + 12, y + 7), f"Поточний курс • {now_str}",
               fill="#0a5cff", font=section_font)
        y += section_h

        d.rectangle([(pad, y), (width - pad, y + head_h)], fill="#f7fbff")
        x = pad + 12
        for name, w in cols_live:
            d.text((x, y + 14), name, fill="#0a2540", font=head_font)
            x += w
        d.line([(pad, y + head_h), (width - pad, y + head_h)], fill="#cbd5e0", width=1)
        y += head_h

        for i, row in enumerate(live):
            if i % 2 == 0:
                d.rectangle([(pad, y), (width - pad, y + row_h)], fill="#fafbfc")
            x = pad + 12
            cells = [row["kind"], row["currency"], f"{row['buy']:.4f}", f"{row['sell']:.4f}"]
            for val, (_, w) in zip(cells, cols_live):
                d.text((x, y + 11), val, fill="#0a2540", font=cell_font)
                x += w
            d.line([(pad, y + row_h), (width - pad, y + row_h)], fill="#d6e8ff", width=1)
            y += row_h
        y += 16

    if archive:
        d.rectangle([(pad, y), (width - pad, y + section_h)], fill="#f0f3f7")
        d.text((pad + 12, y + 7), f"Архів за останні {DAYS} днів",
               fill="#1f2d3d", font=section_font)
        y += section_h

        d.rectangle([(pad, y), (width - pad, y + head_h)], fill="#fafbfc")
        x = pad + 12
        for name, w in cols_arch:
            d.text((x, y + 14), name, fill="#1f2d3d", font=head_font)
            x += w
        d.line([(pad, y + head_h), (width - pad, y + head_h)], fill="#cbd5e0", width=1)
        y += head_h

        for i, row in enumerate(archive):
            if i % 2 == 0:
                d.rectangle([(pad, y), (width - pad, y + row_h)], fill="#fafbfc")
            x = pad + 12
            cells = [row["date"], row["currency"], f"{row['buy']:.4f}", f"{row['sell']:.4f}"]
            for val, (_, w) in zip(cells, cols_arch):
                d.text((x, y + 11), val, fill="#222", font=cell_font)
                x += w
            d.line([(pad, y + row_h), (width - pad, y + row_h)], fill="#eef2f7", width=1)
            y += row_h

    d.rectangle([(0, 0), (width - 1, height - 1)], outline="#cbd5e0", width=1)
    img.save(output_path)


def main():
    _step(1, 4, "Тягну поточний курс")
    live = _fetch_live()

    _step(2, 4, f"Тягну архів за {DAYS} днів")
    archive = _fetch_archive()

    _step(3, 4, f"Малюю таблицю ({len(live)} live + {len(archive)} архів)")
    _render(live, archive, OUTPUT_PATH)

    _step(4, 4, "Зберігаю PNG")
    print(f"DONE:{OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
