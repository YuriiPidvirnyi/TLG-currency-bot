"""
Makes a fresh screenshot of the PrivatBank exchange rate archive via Playwright.
Crops to just the rates table using bounding-box detection + PIL.
"""
import asyncio
from playwright.async_api import async_playwright
from PIL import Image

OUTPUT_PATH = "/app/privatbank_rates.png"
FULL_PAGE_TMP = "/tmp/privatbank_full.png"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("https://privatbank.ua/obmin-valiut", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Click "Архів"
        await page.evaluate("""
            Array.from(document.querySelectorAll('*')).forEach(el => {
                if(el.children.length===0 && el.innerText && el.innerText.trim()==='Архів')
                    el.dispatchEvent(new MouseEvent('click',{bubbles:true}));
            });
        """)
        await page.wait_for_timeout(3000)

        # Click "Таблиця"
        await page.evaluate("""
            Array.from(document.querySelectorAll('*')).forEach(el => {
                if(el.children.length===0 && el.innerText && el.innerText.trim()==='Таблиця')
                    el.dispatchEvent(new MouseEvent('click',{bubbles:true}));
            });
        """)
        await page.wait_for_timeout(2000)

        # Click "Завантажити ще" while available
        for _ in range(10):
            clicked = await page.evaluate("""
                (function(){
                    var els = Array.from(document.querySelectorAll('*'));
                    for(var el of els){
                        if(el.innerText && el.innerText.trim().includes('Завантажити ще')){
                            el.dispatchEvent(new MouseEvent('click',{bubbles:true}));
                            return true;
                        }
                    }
                    return false;
                })()
            """)
            if not clicked:
                break
            await page.wait_for_timeout(1500)

        await page.wait_for_timeout(1000)

        # Locate the rates table bounding box before expanding the viewport
        bbox = await page.evaluate("""
            (function(){
                var selectors = [
                    '[class*="table_container"]',
                    '[class*="archive"]',
                    '[class*="table-macro"]',
                    'table'
                ];
                for(var sel of selectors){
                    var els = document.querySelectorAll(sel);
                    for(var el of els){
                        var rect = el.getBoundingClientRect();
                        var absY = rect.top + window.scrollY;
                        if(rect.width > 300 && rect.height > 100){
                            return {x: Math.round(rect.left), y: Math.round(absY),
                                    w: Math.round(rect.width), h: Math.round(rect.height)};
                        }
                    }
                }
                return null;
            })()
        """)

        await page.set_viewport_size({"width": 1280, "height": 8000})
        await page.wait_for_timeout(500)
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
        print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
