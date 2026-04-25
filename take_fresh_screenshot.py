"""Build the rates archive PNG from PrivatBank's public exchange-rate API.

Replaces the previous Playwright-based scraper. Reasons:
- privatbank.ua redesigned: /rates-archive now 301-redirects to /obmin-valiut
  and the standalone archive table is gone from the public site.
- Headless Chromium on Railway was unreliable (anti-bot, hangs, hydration races).
- The API gives the same data instantly and can't be broken by HTML changes.
"""
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

OUTPUT_PATH = "/app/privatbank_rates.png"
API_URL = "https://api.privatbank.ua/p24api/exchange_rates"
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


def _fetch_with_retry(date_str: str, attempts: int = 4, backoff: float = 1.5) -> dict:
    qs = urllib.parse.urlencode({"json": "", "date": date_str})
    url = f"{API_URL}?{qs}"
    last_err = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode())
                last_err = f"HTTP {resp.status}"
        except Exception as e:
            last_err = str(e)
        time.sleep(backoff * (i + 1))
    raise RuntimeError(f"API failed for {date_str}: {last_err}")


def _collect_rows() -> list:
    today = datetime.now().date()
    rows = []
    for i in range(DAYS):
        d = today - timedelta(days=i)
        ds = d.strftime("%d.%m.%Y")
        try:
            data = _fetch_with_retry(ds)
        except Exception as e:
            print(f"  warn: {ds}: {e}", flush=True)
            continue
        for cur in CURRENCIES:
            for rate in data.get("exchangeRate", []):
                if rate.get("currency") == cur and "saleRate" in rate:
                    rows.append({
                        "date": ds,
                        "currency": f"UAH/{cur}",
                        "buy": rate["purchaseRate"],
                        "sell": rate["saleRate"],
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


def _render(rows: list, output_path: str) -> None:
    if not rows:
        raise RuntimeError("No rates collected from API — nothing to render")

    title_font = _font(24)
    head_font = _font(18)
    cell_font = _font(16)
    sub_font = _font(13)

    cols = [("Дата", 140), ("Валюта", 120), ("Купівля", 130), ("Продаж", 130)]
    pad = 20
    width = pad * 2 + sum(w for _, w in cols)
    title_h = 40
    sub_h = 22
    head_h = 50
    row_h = 40
    height = pad + title_h + sub_h + 10 + head_h + row_h * len(rows) + pad

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    d.text((pad, pad), "Курси валют Приватбанку", fill="black", font=title_font)
    generated = datetime.now().strftime("%d.%m.%Y %H:%M")
    d.text((pad, pad + title_h), f"Архів за останні {DAYS} днів • згенеровано {generated}",
           fill="#666", font=sub_font)

    y = pad + title_h + sub_h + 10
    d.rectangle([(pad, y), (width - pad, y + head_h)], fill="#f0f3f7")
    x = pad + 12
    for name, w in cols:
        d.text((x, y + 14), name, fill="#1f2d3d", font=head_font)
        x += w
    d.line([(pad, y + head_h), (width - pad, y + head_h)], fill="#cbd5e0", width=1)

    y += head_h
    for i, row in enumerate(rows):
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
    _step(1, 4, "Читаю API Приватбанку")
    _step(2, 4, f"Збираю курси за {DAYS} днів")
    rows = _collect_rows()

    _step(3, 4, f"Малюю таблицю з {len(rows)} рядків")
    _render(rows, OUTPUT_PATH)

    _step(4, 4, "Зберігаю PNG")
    print(f"DONE:{OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
