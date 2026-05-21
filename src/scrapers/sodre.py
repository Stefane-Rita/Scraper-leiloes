import asyncio
import logging
import os
from functools import wraps
from typing import Any

from playwright.async_api import Page

from src.browser import SODRE_GOTO_TIMEOUT, SODRE_WAIT_TIMEOUT
from src.filters import is_active_sodre_lot
from src.models import AuctionLot
from src.transform import (
    calc_diff,
    extract_appraisal_from_text,
    format_datetime_br,
    is_opportunity,
    parse_brl,
)

logger = logging.getLogger(__name__)

SODRE_URL = (
    "https://www.sodresantoro.com.br/lotes/em-destaque"
    "?sort=auction_date_init_asc"
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
                            "Sodré: todas as %s tentativas falharam em '%s': %s",
                            max_attempts,
                            func.__name__,
                            exc,
                        )
                        raise
                    logger.warning(
                        "Sodré: tentativa %s/%s falhou em '%s': %s. "
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

# Apenas leilões abertos ou ao vivo; lotes em andamento (sem encerrados)
ACTIVE_LOTS_QUERY: dict[str, Any] = {
    "indices": ["veiculos"],
    "query": {
        "bool": {
            "filter": [
                {
                    "bool": {
                        "should": [
                            {"term": {"auction_status": "online"}},
                            {
                                "bool": {
                                    "must": [{"term": {"auction_status": "aberto"}}],
                                    "must_not": [
                                        {"terms": {"lot_status_id": [5, 6, 7]}}
                                    ],
                                }
                            },
                        ],
                        "minimum_should_match": 1,
                    }
                },
                {"term": {"lot_status": "andamento"}},
                {"bool": {"must_not": [{"term": {"lot_test": True}}]}},
            ]
        }
    },
}


class SodreScraper:
    def __init__(self, page_size: int | None = None, max_pages: int | None = None):
        self.page_size = page_size or int(os.getenv("SODRE_PAGE_SIZE", "100"))
        self.max_pages = max_pages or int(os.getenv("SODRE_MAX_PAGES", "10"))

    @_async_retry(max_attempts=3, delay=3.0)
    async def scrape(self, page: Page) -> list[AuctionLot]:
        logger.info(
            "Sodré: carregando página inicial (timeout=%ss)...",
            SODRE_GOTO_TIMEOUT // 1000,
        )
        await page.goto(SODRE_URL, wait_until="domcontentloaded", timeout=SODRE_GOTO_TIMEOUT)
        await page.wait_for_timeout(SODRE_WAIT_TIMEOUT)

        lots: list[AuctionLot] = []
        seen: set[str] = set()
        skipped = 0
        total_raw = 0

        for page_num in range(self.max_pages):
            body = {
                **ACTIVE_LOTS_QUERY,
                "from": page_num * self.page_size,
                "size": self.page_size,
            }
            try:
                data = await page.evaluate(
                    """async (searchBody) => {
                        const response = await fetch('/api/search-lots', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(searchBody),
                        });
                        if (!response.ok) {
                            return { error: response.status };
                        }
                        return await response.json();
                    }""",
                    body,
                )
            except Exception as exc:
                logger.warning(
                    "Sodré: page.evaluate falhou na página %s: %s", page_num, exc
                )
                break

            if not isinstance(data, dict):
                logger.warning(
                    "Sodré: resposta inesperada na página %s (tipo: %s)",
                    page_num,
                    type(data).__name__,
                )
                break

            if data.get("error"):
                logger.warning(
                    "Sodré: API retornou erro na página %s: status=%s",
                    page_num,
                    data["error"],
                )
                break

            results = data.get("results", [])
            if not results:
                logger.info("Sodré: sem mais resultados após página %s", page_num)
                break

            total_raw += len(results)
            for item in results:
                if not is_active_sodre_lot(item):
                    skipped += 1
                    logger.debug(
                        "Sodré: lote %s filtrado — "
                        "segment_id=%s, segment_slug=%s, auction_status=%s, "
                        "lot_status=%s, lot_status_id=%s, lot_test=%s",
                        item.get("id"),
                        item.get("segment_id"),
                        item.get("segment_slug"),
                        item.get("auction_status"),
                        item.get("lot_status"),
                        item.get("lot_status_id"),
                        item.get("lot_test"),
                    )
                    continue
                lot = self._parse_lot(item)
                if lot and lot.id_externo not in seen:
                    seen.add(lot.id_externo)
                    lots.append(lot)
                    logger.debug("Sodré: lote %s adicionado", lot.id_externo)

            logger.info(
                "Sodré página %s: %s brutos, %s ativos acumulados (ignorados: %s)",
                page_num,
                len(results),
                len(lots),
                skipped,
            )

            if len(results) < self.page_size:
                break

        if total_raw == 0:
            raise RuntimeError(
                "Sodré: nenhum dado foi retornado pela API — "
                "a página pode não ter carregado corretamente ou a API mudou"
            )

        logger.info(
            "Sodré: coleta concluída — %s brutos, %s lotes ativos, %s ignorados",
            total_raw,
            len(lots),
            skipped,
        )
        return lots

    def _parse_lot(self, item: dict[str, Any]) -> AuctionLot | None:
        lot_id = item.get("id") or item.get("index_id")
        if not lot_id:
            return None

        brand = item.get("lot_brand", "")
        model = item.get("lot_model", "")
        title = item.get("lot_title", "")
        year_m = item.get("lot_year_manufacture")
        year_mod = item.get("lot_year_model")
        year_part = f"{year_m}/{year_mod}" if year_m and year_mod else (str(year_m or year_mod or ""))
        modelo = title or f"{brand} {model}".strip()
        if year_part.strip("/"):
            modelo = f"{modelo} ({year_part})".strip()

        lance = parse_brl(item.get("bid_actual"))
        avaliado = extract_appraisal_from_text(item.get("lot_description", ""))
        
        # Fallbacks para preço de avaliação
        if avaliado is None:
            # 1. Tenta bid_initial se não há lances
            inicial = parse_brl(item.get("bid_initial"))
            if inicial and inicial > 0 and item.get("bid_has_bid") is False:
                avaliado = inicial
                logger.debug(
                    "Sodré: lote %s — avaliação não encontrada; usando bid_initial: R$ %.2f",
                    lot_id, avaliado
                )
        
        # 2. Se ainda não tem avaliação, tenta estimar como 1.2x o lance atual (12% acima)
        if avaliado is None and lance and lance > 0:
            avaliado = lance * 1.2
            logger.debug(
                "Sodré: lote %s — avaliação não encontrada; usando estimativa (lance * 1.2): R$ %.2f",
                lot_id, avaliado
            )

        diff_rs, diff_pct = calc_diff(lance, avaliado)

        condicao_veiculo = " | ".join(
            filter(
                None,
                [
                    item.get("lot_sinister"),
                    item.get("lot_origin"),
                    item.get("lot_category"),
                ],
            )
        )

        data_fim = item.get("lot_date_end") or item.get("auction_date_end") or ""
        condicao_leilao = " | ".join(
            filter(
                None,
                [
                    item.get("auction_status"),
                    item.get("lot_status"),
                    item.get("auction_name"),
                ],
            )
        )

        return AuctionLot(
            fonte="Sodré Santoro",
            modelo_veiculo=modelo,
            lance_atual=lance,
            preco_avaliado=avaliado,
            diferenca_rs=diff_rs,
            diferenca_pct=diff_pct,
            data_leilao=format_datetime_br(item.get("auction_date_init", "")),
            data_finalizacao=format_datetime_br(data_fim),
            oportunidade=is_opportunity(lance, avaliado),
            condicao_veiculo=condicao_veiculo,
            condicao_leilao=condicao_leilao,
            local_leilao=item.get("lot_location") or item.get("lot_location_address", ""),
            id_externo=str(lot_id),
        )
