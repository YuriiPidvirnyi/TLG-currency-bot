import asyncio
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from PIL import Image

OUTPUT_PATH = "/app/privatbank_rates.png"
FULL_PAGE_TMP = "/tmp/privatbank_full.png"
URL = "https://privatbank.ua/obmin-valiut"


def _step(n: int, total: int, desc: str) -> None:
    print(f"STEP:{n}:{total}:{desc}", flush=True)


async def _click_text(page, text: str, timeout_ms: int = 20000) -> None:
    """Real mouse click via Chrome DevTools Protocol — triggers all React handlers.
    Tries an exact text match first, falls back to contains."""
    try:
        loc = page.get_by_text(text, exact=True).first
        await loc.wait_for(state="visible", timeout=timeout_ms)
        await loc.scroll_into_view_if_needed()
        await loc.click(timeout=5000)
    except PWTimeout:
        loc = page.locator(f"text={text}").first
        await loc.wait_for(state="visible", timeout=5000)
        await loc.scroll_into_view_if_needed()
        await loc.click(timeout=5000)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
            ],
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        _step(1, 5, "Відкриваю сторінку Приватбанку")
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        # Let React hydrate so click handlers are attached
        await page.wait_for_timeout(2500)

        _step(2, 5, "Переходжу в Архів")
        await _click_text(page, "Архів", timeout_ms=20000)
        # Wait for the Архів view to render (Таблиця button is part of it)
        await page.wait_for_timeout(1500)

        _step(3, 5, "Вмикаю режим таблиці")
        await _click_text(page, "Таблиця", timeout_ms=15000)
        # Wait for actual table rows to appear — proves we are on the right tab
        try:
            await page.locator("table tr, [class*='table'] tr").first.wait_for(
                state="visible", timeout=15000
            )
        except PWTimeout:
            pass
        await page.wait_for_timeout(500)

        _step(4, 5, "Завантажую всі записи")
        for _ in range(10):
            try:
                more = page.get_by_text("Завантажити ще", exact=False).first
                if not await more.is_visible(timeout=1500):
                    break
                await more.scroll_into_view_if_needed()
                await more.click(timeout=3000)
                await page.wait_for_timeout(1000)
            except PWTimeout:
                break

        await page.wait_for_timeout(500)

        _step(5, 5, "Роблю скріншот та обробляю")
        bbox = await page.evaluate("""(function () {
            var selectors = [
                '[class*="table_container"]',
                '[class*="archive"]',
                '[class*="table-macro"]',
                'table'
            ];
            for (var sel of selectors) {
                var els = document.querySelectorAll(sel);
                for (var el of els) {
                    var rect = el.getBoundingClientRect();
                    var absY = rect.top + window.scrollY;
                    if (rect.width > 300 && rect.height > 100) {
                        return {
                            x: Math.round(rect.left), y: Math.round(absY),
                            w: Math.round(rect.width), h: Math.round(rect.height)
                        };
                    }
                }
            }
            return null;
        })()""")

        await page.screenshot(path=FULL_PAGE_TMP, full_page=True)
        await browser.close()

        img = Image.open(FULL_PAGE_TMP)
        if bbox:
            pad = 20
            x1 = max(0, bbox["x"] - pad)
            y1 = max(0, bbox["y"] - pad)
            x2 = min(img.width, bbox["x"] + bbox["w"] + pad)
            y2 = min(img.height, bbox["y"] + bbox["h"] + pad)
            img = img.crop((x1, y1, x2, y2))
        img.save(OUTPUT_PATH)
        print(f"DONE:{OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
