from contextlib import asynccontextmanager
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@asynccontextmanager
async def browser_session(headless: bool = True):
    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(headless=headless)
        context: BrowserContext = await browser.new_context(
            locale="pt-BR",
            user_agent=USER_AGENT,
        )
        page: Page = await context.new_page()
        try:
            yield browser, context, page
        finally:
            await browser.close()
