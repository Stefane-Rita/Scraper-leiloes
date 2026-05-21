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
    copart_count = 0
    sodre_count = 0

    async with browser_session(headless=True) as (browser, context):
        copart_page = await context.new_page()
        logger.info("Coletando Copart...")
        try:
            copart_lots = await copart.scrape(copart_page)
            copart_count = len(copart_lots)
            lots.extend(copart_lots)
            logger.info("Copart: %s lotes coletados", copart_count)
        except Exception as exc:
            logger.error("Copart: coleta falhou após todas as tentativas: %s", exc)
        finally:
            await copart_page.close()

        sodre_page = await context.new_page()
        logger.info("Coletando Sodré Santoro...")
        try:
            sodre_lots = await sodre.scrape(sodre_page)
            sodre_count = len(sodre_lots)
            lots.extend(sodre_lots)
            logger.info("Sodré: %s lotes coletados", sodre_count)
        except Exception as exc:
            logger.error("Sodré: coleta falhou após todas as tentativas: %s", exc)
        finally:
            await sodre_page.close()

    logger.info(
        "Coleta concluída — Copart: %s, Sodré: %s, Total: %s lotes",
        copart_count,
        sodre_count,
        len(lots),
    )
    lots.sort(key=lambda x: (x.fonte, x.data_leilao, x.modelo_veiculo))
    return lots


def run_pipeline() -> int:
    lots = asyncio.run(collect_lots())

    if not lots:
        logger.warning(
            "Nenhum lote foi coletado de nenhuma fonte — "
            "a sincronização com a planilha será ignorada para evitar apagar dados existentes"
        )
        return 0

    logger.info("Total coletado: %s lotes — iniciando sincronização com a planilha...", len(lots))
    try:
        SheetsClient().sync(lots)
    except Exception as exc:
        raise RuntimeError(
            f"Falha ao sincronizar {len(lots)} lotes com a planilha: {exc}"
        ) from exc

    return len(lots)
