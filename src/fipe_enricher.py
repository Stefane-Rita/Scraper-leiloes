"""
Enriquece lotes Sodré Santoro sem preço avaliado usando a tabela FIPE.
Cache persistente em aba separada do Google Sheets para economizar chamadas à API.
"""
import logging
import re
from datetime import date, timedelta
from typing import Optional

import gspread

from src.fipe import FipeClient
from src.models import AuctionLot

logger = logging.getLogger(__name__)

CACHE_SHEET_NAME = "FIPE_Cache"
CACHE_TTL_DAYS = 30  # preços FIPE mudam mensalmente

# Colunas da aba de cache
_CACHE_HEADERS = ["chave", "preco", "data_cache"]


def _lot_cache_key(lot: AuctionLot) -> str:
    """Chave canônica: 'marca|modelo|ano'"""
    brand = (lot.lot_brand or "").strip().lower()
    model = (lot.lot_model or "").strip().lower()
    if brand and model:
        key = f"{brand}|{model}"
    else:
        key = (lot.modelo_veiculo or "").strip().lower()

    year = ""
    if lot.lot_year is not None:
        year = str(lot.lot_year)
    else:
        match = re.search(r"\((\d{4})", lot.modelo_veiculo or "")
        if match:
            year = match.group(1)
    return f"{key}|{year}"


def _vehicle_type_hint(lot: AuctionLot) -> str:
    desc = (lot.condicao_veiculo or "").lower()
    modelo = (lot.modelo_veiculo or "").lower()
    if any(k in desc + modelo for k in ("moto", "biz", "cg ", "titan", "bros", "fan ")):
        return "motorcycles"
    if any(k in desc + modelo for k in ("caminhão", "caminhao", "ônibus", "onibus", "truck")):
        return "trucks"
    return "cars"


class FipeEnricher:
    def __init__(self, sheets_client=None):
        """
        sheets_client: instância de SheetsClient já inicializada.
        Se None, enriquecimento funciona mas sem cache persistente.
        """
        self._sheets = sheets_client
        self._cache_sheet: Optional[gspread.Worksheet] = None
        self._cache: dict[str, Optional[float]] = {}  # chave → preço
        self._dirty: set[str] = set()  # chaves novas a gravar

    def _load_cache_from_sheet(self):
        """Lê o cache da aba FIPE_Cache no Sheets."""
        if not self._sheets:
            return
        try:
            spreadsheet = self._sheets.spreadsheet
            try:
                ws = spreadsheet.worksheet(CACHE_SHEET_NAME)
            except gspread.WorksheetNotFound:
                ws = spreadsheet.add_worksheet(
                    title=CACHE_SHEET_NAME, rows=5000, cols=3
                )
                ws.append_row(_CACHE_HEADERS)

            self._cache_sheet = ws
            records = ws.get_all_records()
            today = date.today()
            valid = 0

            for row in records:
                chave = str(row.get("chave", ""))
                preco_str = str(row.get("preco", ""))
                data_str = str(row.get("data_cache", ""))

                if not chave:
                    continue
                try:
                    cached_date = date.fromisoformat(data_str)
                    if (today - cached_date).days > CACHE_TTL_DAYS:
                        continue  # expirado
                    self._cache[chave] = float(preco_str) if preco_str else None
                    valid += 1
                except (ValueError, TypeError):
                    continue

            logger.info("FIPE cache: %s entradas válidas carregadas do Sheets", valid)
        except Exception as e:
            logger.warning("Não foi possível carregar cache FIPE: %s", e)

    def _flush_cache_to_sheet(self):
        """Grava entradas novas no Sheets."""
        if not self._cache_sheet or not self._dirty:
            return
        try:
            today = date.today().isoformat()
            rows = [
                [key, str(self._cache[key]) if self._cache[key] else "", today]
                for key in self._dirty
            ]
            self._cache_sheet.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info("FIPE cache: %s novas entradas gravadas", len(rows))
            self._dirty.clear()
        except Exception as e:
            logger.warning("Falha ao gravar cache FIPE: %s", e)

    async def enrich(self, lots: list[AuctionLot]) -> int:
        """
        Enriquece lotes sem preco_avaliado usando FIPE.
        Retorna o número de lotes enriquecidos.
        """
        self._load_cache_from_sheet()

        # Filtra só lotes Sodré sem preço
        to_enrich = [
            lot for lot in lots
            if lot.fonte == "Sodré Santoro" and not lot.preco_avaliado
        ]

        if not to_enrich:
            logger.info("FIPE: nenhum lote precisando de enriquecimento")
            return 0

        logger.info("FIPE: enriquecendo %s lotes sem preço avaliado", len(to_enrich))

        # Deduplica por chave para economizar chamadas
        unique: dict[str, list[AuctionLot]] = {}
        for lot in to_enrich:
            key = _lot_cache_key(lot)
            unique.setdefault(key, []).append(lot)

        logger.info("FIPE: %s chaves únicas (de %s lotes)", len(unique), len(to_enrich))

        enriched = 0
        fipe = FipeClient()

        try:
            for key, group in unique.items():
                lot = group[0]  # representante do grupo

                # Verifica cache em memória primeiro
                if key in self._cache:
                    price = self._cache[key]
                else:
                    # Extrai componentes do modelo para busca FIPE
                    brand = lot.lot_brand or ""
                    model = lot.lot_model or ""
                    if not brand or not model:
                        parts = (lot.modelo_veiculo or "").split()
                        brand = brand or (parts[0] if parts else "")
                        model = model or " ".join(parts[1:])

                    # Remove o ano do model se estiver no final "(2019/2020)"
                    model = re.sub(r"\s*\(\d{4}.*?\)", "", model).strip()

                    year = lot.lot_year
                    if year is None:
                        year_match = re.search(r"\((\d{4})", lot.modelo_veiculo or "")
                        if year_match:
                            year = int(year_match.group(1))

                    price = await fipe.lookup(
                        brand=brand,
                        model=model,
                        year=year,
                        vtype_hint=_vehicle_type_hint(lot),
                    )
                    self._cache[key] = price
                    self._dirty.add(key)

                if price:
                    for l in group:
                        l.preco_avaliado = price
                        # Recalcula diferença agora que temos o preço
                        from src.transform import calc_diff, is_opportunity
                        l.diferenca_rs, l.diferenca_pct = calc_diff(l.lance_atual, price)
                        l.oportunidade = is_opportunity(l.lance_atual, price)
                    enriched += len(group)

        finally:
            await fipe.aclose()

        self._flush_cache_to_sheet()
        logger.info("FIPE: %s lotes enriquecidos com sucesso", enriched)
        return enriched