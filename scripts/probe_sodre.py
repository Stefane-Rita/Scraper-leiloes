"""Inspeciona resposta da API Sodré Santoro."""
import asyncio
import json
from playwright.async_api import async_playwright

URL = "https://www.sodresantoro.com.br/lotes/em-destaque?sort=auction_date_init_asc"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="pt-BR")
        page = await ctx.new_page()
        captured = []

        async def on_response(resp):
            if "search-lots" in resp.url and resp.status == 200:
                try:
                    captured.append(await resp.json())
                except Exception:
                    pass

        page.on("response", on_response)
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(8000)
        await browser.close()

    if not captured:
        print("Nenhuma resposta capturada")
        return
    data = captured[-1]
    results = data.get("results", [])
    print(f"Total lotes: {len(results)}")
    if results:
        print(json.dumps(results[0], indent=2, ensure_ascii=False)[:4000])
    with open("scripts/sodre_sample.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
