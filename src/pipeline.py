import asyncio
import logging

from src.browser import browser_session
from src.models import AuctionLot
from src.scrapers import CopartScraper, SodreScraper
from src.sheets import SheetsClient
from src.fipe_enricher import FipeEnricher


logger = logging.getLogger(__name__)


async def collect_lots() -> list[AuctionLot]:
    copart = CopartScraper()
    sodre = SodreScraper()
    lots: list[AuctionLot] = []
    copart_count = 0
    sodre_count = 0

    async with browser_session(headless=True) as (browser, context):
        # Criar páginas para ambos os scrapers
        copart_page = await context.new_page()
        sodre_page = await context.new_page()

        try:
            # Coletar em paralelo
            copart_lots, sodre_lots = await asyncio.gather(
                _collect_copart(copart, copart_page),
                _collect_sodre(sodre, sodre_page),
                return_exceptions=True,
            )

            # Processar resultados
            if isinstance(copart_lots, Exception):
                logger.error("Copart: coleta falhou: %s", copart_lots)
            else:
                copart_count = len(copart_lots)
                lots.extend(copart_lots)
                logger.info("Copart: %s lotes coletados", copart_count)

            if isinstance(sodre_lots, Exception):
                logger.error("Sodré: coleta falhou: %s", sodre_lots)
            else:
                sodre_count = len(sodre_lots)
                lots.extend(sodre_lots)
                logger.info("Sodré: %s lotes coletados", sodre_count)

        finally:
            await copart_page.close()
            await sodre_page.close()

    logger.info(
        "Coleta concluída — Copart: %s, Sodré: %s, Total: %s lotes",
        copart_count,
        sodre_count,
        len(lots),
    )
    lots.sort(key=lambda x: (x.fonte, x.data_leilao, x.modelo_veiculo))
    return lots


async def _collect_copart(scraper: "CopartScraper", page) -> list[AuctionLot]:
    """Coletar lotes Copart."""
    logger.info("Coletando Copart...")
    return await scraper.scrape(page)


async def _collect_sodre(scraper: "SodreScraper", page) -> list[AuctionLot]:
    """Coletar lotes Sodré."""
    logger.info("Coletando Sodré Santoro...")
    return await scraper.scrape(page)


async def run_pipeline_async() -> int:
    lots = await collect_lots()

    if not lots:
        logger.warning(...)
        return 0

    sheets = SheetsClient()

    # ← bloco novo
    try:
        enriched = await FipeEnricher(sheets).enrich(lots)
        logger.info("FIPE: %s lotes enriquecidos", enriched)
    except Exception as exc:
        logger.warning("Enriquecimento FIPE falhou, continuando sem: %s", exc)
    # ← fim do bloco novo

    logger.info("Total coletado: %s lotes — iniciando sincronização...", len(lots))
    try:
        await asyncio.to_thread(sheets.sync, lots)
    except Exception as exc:
        raise RuntimeError(
            f"Falha ao sincronizar {len(lots)} lotes com a planilha: {exc}"
        ) from exc

    return len(lots)


def run_pipeline() -> int:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_pipeline_async())
    raise RuntimeError(
        "run_pipeline() não pode ser chamado dentro de um loop já em execução; use run_pipeline_async() em código async"
    )
