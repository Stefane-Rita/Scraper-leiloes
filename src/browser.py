import logging
from contextlib import asynccontextmanager

from playwright.async_api import Browser, BrowserContext, async_playwright

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Timeouts (ms) — generous to handle slow networks and heavy pages
COPART_GOTO_TIMEOUT = 180_000   # 3 minutes
SODRE_GOTO_TIMEOUT = 120_000    # 2 minutes
COPART_WAIT_TIMEOUT = 6_000
SODRE_WAIT_TIMEOUT = 3_000


@asynccontextmanager
async def browser_session(headless: bool = True):
    logger.debug("Iniciando sessão do browser (headless=%s)", headless)
    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context: BrowserContext = await browser.new_context(
            locale="pt-BR",
            user_agent=USER_AGENT,
        )
        try:
            yield browser, context
        except Exception:
            logger.exception("Erro inesperado durante a sessão do browser")
            raise
        finally:
            logger.debug("Encerrando sessão do browser")
            await browser.close()
