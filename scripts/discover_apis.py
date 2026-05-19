"""Descobre endpoints de API interceptando tráfego de rede."""
import asyncio
import json
from playwright.async_api import async_playwright

URLS = [
    ("sodre", "https://www.sodresantoro.com.br/lotes/em-destaque?sort=auction_date_init_asc"),
    ("copart", "https://www.copart.com.br/search/leil%C3%A3o/?displayStr=Leil%C3%A3o&from=%2FvehicleFinder"),
]


async def capture(site: str, url: str):
    apis = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        async def on_response(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct or "graphql" in response.url.lower():
                try:
                    body = await response.text()
                    if len(body) > 100 and any(
                        k in body.lower()
                        for k in ("lote", "lot", "auction", "leil", "bid", "lance")
                    ):
                        apis.append(
                            {
                                "url": response.url[:200],
                                "status": response.status,
                                "sample": body[:800],
                            }
                        )
                except Exception:
                    pass

        page.on("response", on_response)
        try:
            await page.goto(url, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"{site} navigation error: {e}")
        await browser.close()
    return apis


async def main():
    for site, url in URLS:
        print(f"\n=== {site.upper()} ===")
        apis = await capture(site, url)
        for i, a in enumerate(apis[:15]):
            print(f"\n[{i}] {a['url']} ({a['status']})")
            print(a["sample"][:400])


if __name__ == "__main__":
    asyncio.run(main())
