import asyncio
import logging
import os
from functools import wraps
from typing import Any

from playwright.async_api import Page

from src.browser import COPART_GOTO_TIMEOUT, COPART_WAIT_TIMEOUT
from src.filters import is_active_copart_lot
from src.models import AuctionLot
from src.transform import calc_diff, format_datetime_br, is_opportunity, parse_brl

logger = logging.getLogger(__name__)

COPART_SEARCH_URL = (
    "https://www.copart.com.br/search/leil%C3%A3o/"
    "?displayStr=Leil%C3%A3o&from=%2FvehicleFinder"
)


def _async_retry(max_attempts: int = 3, delay: float = 2.0):
    """Decorator de retry assíncrono para métodos de scraper."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts:
                        logger.error(
                            "Copart: todas as %s tentativas falharam em '%s': %s",
                            max_attempts,
                            func.__name__,
                            exc,
                        )
                        raise
                    logger.warning(
                        "Copart: tentativa %s/%s falhou em '%s': %s. "
                        "Aguardando %.1fs antes de tentar novamente...",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
        return wrapper
    return decorator


class CopartScraper:
    """Coleta lotes via API DataTables (POST form-urlencoded) disparada pela página de busca."""

    def __init__(self, max_pages: int | None = None):
        self.max_pages = max_pages or int(os.getenv("COPART_MAX_PAGES", "50"))

    @_async_retry(max_attempts=3, delay=3.0)
    async def scrape(self, page: Page) -> list[AuctionLot]:
        batches: list[list[dict[str, Any]]] = []

        async def on_response(response):
            if "lots/search" not in response.url or response.status != 200:
                return
            try:
                payload = await response.json()
                content = (
                    payload.get("data", {})
                    .get("results", {})
                    .get("content", [])
                )
                if content:
                    batches.append(content)
                    logger.debug(
                        "Copart: capturou batch com %s itens (total batches: %s)",
                        len(content),
                        len(batches),
                    )
            except Exception as exc:
                logger.warning("Copart: falha ao parsear resposta da API: %s", exc)

        page.on("response", on_response)

        logger.info(
            "Copart: carregando página de busca (timeout=%ss)...",
            COPART_GOTO_TIMEOUT // 1000,
        )
        await page.goto(COPART_SEARCH_URL, wait_until="load", timeout=COPART_GOTO_TIMEOUT)
        await page.wait_for_timeout(COPART_WAIT_TIMEOUT)

        for page_num in range(1, self.max_pages):
            next_btn = page.locator("#serverSideDataTable_next:not(.disabled)")
            if await next_btn.count() == 0:
                logger.info("Copart: sem mais páginas após página %s", page_num)
                break
            try:
                await next_btn.scroll_into_view_if_needed(timeout=5_000)
                await next_btn.click(timeout=10_000)
                await page.wait_for_timeout(5_000)
                logger.info("Copart: navegou para página %s", page_num + 1)
            except Exception as exc:
                logger.warning(
                    "Copart: paginação interrompida na página %s: %s",
                    page_num,
                    exc,
                )
                break

        if not batches:
            raise RuntimeError(
                "Copart: nenhum batch de dados foi capturado — "
                "a API pode não ter respondido ou a estrutura da página mudou"
            )

        lots: list[AuctionLot] = []
        seen: set[str] = set()
        skipped = 0
        for batch in batches:
            for item in batch:
                if not is_active_copart_lot(item):
                    skipped += 1
                    continue
                lot = self._parse_lot(item)
                if lot and lot.id_externo not in seen:
                    seen.add(lot.id_externo)
                    lots.append(lot)

        logger.info(
            "Copart: %s respostas API, %s lotes ativos (ignorados: %s)",
            len(batches),
            len(lots),
            skipped,
        )
        return lots

    def _parse_lot(self, item: dict[str, Any]) -> AuctionLot | None:
        lot_id = item.get("ln")
        if not lot_id:
            return None

        vehicle_type = item.get("vehicleType", "")
        if vehicle_type:
            lower = vehicle_type.lower()
            if not any(k in lower for k in ("autom", "moto", "caminh", "utilit", "van", "suv")):
                return None

        modelo = item.get("ld") or f"{item.get('mkn', '')} {item.get('lm', '')}".strip()
        lance = parse_brl(item.get("hb"))
        avaliado = parse_brl(item.get("la"))
        diff_rs, diff_pct = calc_diff(lance, avaliado)

        condicao_veiculo = " | ".join(
            filter(
                None,
                [
                    item.get("damageClassification"),
                    item.get("lossType"),
                    item.get("drivabilityRating"),
                    item.get("stt") or item.get("td"),
                ],
            )
        )

        status_leilao = "Ao vivo" if item.get("upcoming") is False else "Próximo leilão"
        if item.get("bf"):
            status_leilao = "Leilão"

        return AuctionLot(
            fonte="Copart",
            modelo_veiculo=modelo,
            lance_atual=lance,
            preco_avaliado=avaliado,
            diferenca_rs=diff_rs,
            diferenca_pct=diff_pct,
            data_leilao=format_datetime_br(item.get("ad", "")),
            data_finalizacao=format_datetime_br(item.get("at", "")),
            oportunidade=is_opportunity(lance, avaliado),
            condicao_veiculo=condicao_veiculo,
            condicao_leilao=f"{item.get('saleType', 'Leilão')} | {status_leilao}",
            local_leilao=item.get("syn") or item.get("yn", ""),
            id_externo=str(lot_id),
        )
