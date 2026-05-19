import asyncio
import logging

from src.browser import browser_session
from src.models import AuctionLot
from src.scrapers import CopartScraper, SodreScraper
from src.sheets import SheetsClient

logger = logging.getLogger(__name__)


async def collect_lots() -> list[AuctionLot]:
    copart = CopartScraper()
    sodre = SodreScraper()
    lots: list[AuctionLot] = []

    async with browser_session(headless=True) as (_, context, _):
        copart_page = await context.new_page()
        logger.info("Coletando Copart...")
        lots.extend(await copart.scrape(copart_page))
        await copart_page.close()

        sodre_page = await context.new_page()
        logger.info("Coletando Sodré Santoro...")
        lots.extend(await sodre.scrape(sodre_page))
        await sodre_page.close()

    lots.sort(key=lambda x: (x.fonte, x.data_leilao, x.modelo_veiculo))
    return lots


def run_pipeline() -> int:
    lots = asyncio.run(collect_lots())
    logger.info("Total coletado: %s lotes", len(lots))
    SheetsClient().sync(lots)
    return len(lots)
