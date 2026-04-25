"""
Робить свіжий скріншот архіву курсів Приватбанку через Playwright.
"""
import asyncio
from playwright.async_api import async_playwright

OUTPUT_PATH = "/app/privatbank_rates.png"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto("https://privatbank.ua/obmin-valiut", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Клік Архів
        await page.evaluate("""
            Array.from(document.querySelectorAll('*')).forEach(el => {
                if(el.children.length===0 && el.innerText && el.innerText.trim()==='Архів')
                    el.dispatchEvent(new MouseEvent('click',{bubbles:true}));
            });
        """)
        await page.wait_for_timeout(3000)

        # Клік Таблиця
        await page.evaluate("""
            Array.from(document.querySelectorAll('*')).forEach(el => {
                if(el.children.length===0 && el.innerText && el.innerText.trim()==='Таблиця')
                    el.dispatchEvent(new MouseEvent('click',{bubbles:true}));
            });
        """)
        await page.wait_for_timeout(2000)

        # Завантажити ще
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
        await page.set_viewport_size({"width": 1280, "height": 8000})
        await page.screenshot(path=OUTPUT_PATH, full_page=True)
        await browser.close()
        print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
