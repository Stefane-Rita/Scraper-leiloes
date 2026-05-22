import asyncio
import logging

from src.browser import browser_session
from src.fipe_enricher import FipeEnricher
from src.models import AuctionLot
from src.scrapers import CopartScraper, SodreScraper
from src.sheets import SheetsClient

logger = logging.getLogger(__name__)


async def collect_lots() -> list[AuctionLot]:
    copart = CopartScraper()
    sodre = SodreScraper()
    lots: list[AuctionLot] = []

    async with browser_session(headless=True) as (playwright, browser, context):
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


async def run_pipeline_async() -> int:
    lots = await collect_lots()
    logger.info("Total coletado: %s lotes", len(lots))

    sheets = SheetsClient()

    # Enriquece lotes Sodré sem preço avaliado via FIPE
    enriched = await FipeEnricher(sheets_client=sheets).enrich(lots)
    logger.info("FIPE: %s lotes enriquecidos", enriched)

    await asyncio.to_thread(sheets.sync, lots)
    return len(lots)


def run_pipeline() -> int:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_pipeline_async())
    raise RuntimeError(
        "run_pipeline() não pode ser chamado dentro de um loop já em execução; use run_pipeline_async() em código async"
    )