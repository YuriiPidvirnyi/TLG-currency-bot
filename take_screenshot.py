"""
Окремий скрипт для скріншота таблиці курсів Приватбанку.
Запускається ботом у subprocess.
"""
import asyncio
from playwright.async_api import async_playwright

OUTPUT_PATH = "/tmp/privatbank_rates.png"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        await page.goto("https://privatbank.ua/obmin-valiut", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Клік на "Архів" через JS (елемент може бути прихований)
        await page.evaluate("""
            (function(){
                var all = Array.from(document.querySelectorAll('a, button, span, div'));
                for(var el of all){
                    if(el.innerText && el.innerText.trim() === 'Архів'){
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                        return;
                    }
                }
            })()
        """)
        await page.wait_for_timeout(3000)

        # Клік на "Таблиця"
        await page.evaluate("""
            (function(){
                var all = Array.from(document.querySelectorAll('a, button, span, div'));
                for(var el of all){
                    if(el.innerText && el.innerText.trim() === 'Таблиця'){
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                        return;
                    }
                }
            })()
        """)
        await page.wait_for_timeout(2000)

        # Клікаємо "Завантажити ще" поки є
        for _ in range(10):
            clicked = await page.evaluate("""
                (function(){
                    var all = Array.from(document.querySelectorAll('a, button, span, div'));
                    for(var el of all){
                        if(el.innerText && el.innerText.trim().includes('Завантажити ще')){
                            el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
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

        # Знаходимо контейнер таблиці через клас
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

        # Повний скріншот
        await page.set_viewport_size({"width": 1280, "height": 8000})
        await page.wait_for_timeout(500)
        await page.screenshot(path="/tmp/full_page.png", full_page=True)

        # Кроп таблиці
        if bbox:
            from PIL import Image
            img = Image.open("/tmp/full_page.png")
            padding = 20
            x1 = max(0, bbox["x"] - padding)
            y1 = max(0, bbox["y"] - padding)
            x2 = min(img.width, bbox["x"] + bbox["w"] + padding)
            y2 = min(img.height, bbox["y"] + bbox["h"] + padding)
            cropped = img.crop((x1, y1, x2, y2))
            cropped.save(OUTPUT_PATH)
        else:
            # Якщо не знайшли — зберігаємо видиму частину навколо середини
            from PIL import Image
            img = Image.open("/tmp/full_page.png")
            img.save(OUTPUT_PATH)

        await browser.close()
        print(f"Screenshot saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
