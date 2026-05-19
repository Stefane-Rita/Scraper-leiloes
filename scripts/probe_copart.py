"""Inspeciona APIs Copart Brasil via Playwright."""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://www.copart.com.br/search/leil%C3%A3o/?displayStr=Leil%C3%A3o&from=%2FvehicleFinder"


async def main():
    apis = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = await ctx.new_page()

        async def on_response(resp):
            url = resp.url
            if resp.status != 200:
                return
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return
            if any(k in url for k in ("lot", "search", "public/data", "inventory")):
                try:
                    body = await resp.json()
                    apis.append({"url": url, "keys": list(body.keys()) if isinstance(body, dict) else type(body).__name__})
                    if "lot" in url.lower() or "search" in url.lower():
                        with open("scripts/copart_sample.json", "w", encoding="utf-8") as f:
                            json.dump(body, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        page.on("response", on_response)
        await page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(15000)
        await browser.close()

    for a in apis:
        print(a)


if __name__ == "__main__":
    asyncio.run(main())
