import logging
import os
from typing import Any

from playwright.async_api import Page

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
        self.max_pages = max_pages or int(os.getenv("SODRE_MAX_PAGES", "30"))

    async def scrape(self, page: Page) -> list[AuctionLot]:
        await page.goto(SODRE_URL, wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(3_000)

        lots: list[AuctionLot] = []
        seen: set[str] = set()
        skipped = 0

        for page_num in range(self.max_pages):
            body = {
                **ACTIVE_LOTS_QUERY,
                "from": page_num * self.page_size,
                "size": self.page_size,
            }
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

            if data.get("error"):
                logger.warning("Sodré API erro na página %s: %s", page_num, data["error"])
                break

            results = data.get("results", [])
            if not results:
                break

            for item in results:
                if not is_active_sodre_lot(item):
                    skipped += 1
                    continue
                lot = self._parse_lot(item)
                if lot and lot.id_externo not in seen:
                    seen.add(lot.id_externo)
                    lots.append(lot)

            logger.info(
                "Sodré página %s: %s brutos, %s ativos acumulados (ignorados: %s)",
                page_num,
                len(results),
                len(lots),
                skipped,
            )

            if len(results) < self.page_size:
                break

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
        if avaliado is None:
            inicial = parse_brl(item.get("bid_initial"))
            if inicial and inicial > 0 and item.get("bid_has_bid") is False:
                avaliado = inicial

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
