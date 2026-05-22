import asyncio
import logging
import os
import re
import unicodedata
from difflib import get_close_matches
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FIPE_BASE = "https://fipe.parallelum.com.br/api/v2"
VEHICLE_TYPES = ["cars", "motorcycles", "trucks"]

# Mapeamento para normalizar marcas comuns entre Sodré e FIPE
BRAND_ALIASES: dict[str, str] = {
    "vw": "vw - volkswagen",
    "volkswagen": "vw - volkswagen",
    "gm": "chevrolet",
    "general motors": "chevrolet",
    "mercedes": "mercedes-benz",
    "land rover": "land-rover",
    "bmw motorrad": "bmw",
}


def _normalize(text: str) -> str:
    """Lowercase, remove acentos, colapsa espaços."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_fipe_price(price_str: str) -> Optional[float]:
    """'R$ 32.500,00' → 32500.0"""
    if not price_str:
        return None
    cleaned = re.sub(r"[R$\s\.]", "", price_str).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _best_match(query: str, candidates: list[str]) -> Optional[str]:
    """Retorna o candidato mais próximo usando normalização + difflib."""
    q = _normalize(BRAND_ALIASES.get(_normalize(query), query))
    if not q:
        return None
    norm_map = {_normalize(c): c for c in candidates if c}

    # 1. Correspondência exata
    if q in norm_map:
        return norm_map[q]

    # 2. Contém (query dentro do candidato ou vice-versa)
    for norm, original in norm_map.items():
        if q in norm or norm in q:
            return original

    # 3. Fuzzy
    matches = get_close_matches(q, list(norm_map.keys()), n=1, cutoff=0.6)
    if matches:
        return norm_map[matches[0]]

    return None


def _best_year_code(years: list[dict], target: Optional[int]) -> Optional[str]:
    """Encontra o yearId FIPE ('2019-1') mais próximo do ano alvo."""
    if not years:
        return None
    if target is None:
        return years[0]["code"]

    # Tenta match exato
    for y in years:
        if y["code"].split("-")[0] == str(target):
            return y["code"]

    # Ano mais próximo
    def dist(y):
        try:
            return abs(int(y["code"].split("-")[0]) - target)
        except (ValueError, IndexError):
            return 9999

    return min(years, key=dist)["code"]


class FipeClient:
    """
    Cliente assíncrono para a API FIPE com cache em memória por execução.
    Cache em memória evita chamadas duplicadas para o mesmo veículo na mesma run.
    """

    def __init__(self, token: Optional[str] = None):
        tok = token or os.getenv("FIPE_API_TOKEN")
        headers = {"Accept": "application/json"}
        if tok:
            headers["X-Subscription-Token"] = tok
        self._http = httpx.AsyncClient(
            base_url=FIPE_BASE, headers=headers, timeout=15.0
        )
        self._brands: dict[str, list[dict]] = {}   # vtype → lista
        self._models: dict[tuple, list[dict]] = {}  # (vtype, brand_id) → lista
        self._price_cache: dict[tuple, Optional[float]] = {}

    async def aclose(self):
        await self._http.aclose()

    async def _brands_for(self, vtype: str) -> list[dict]:
        if vtype not in self._brands:
            r = await self._http.get(f"/{vtype}/brands")
            self._brands[vtype] = r.json() if r.status_code == 200 else []
        return self._brands[vtype]

    async def _models_for(self, vtype: str, brand_id: str) -> list[dict]:
        key = (vtype, brand_id)
        if key not in self._models:
            r = await self._http.get(f"/{vtype}/brands/{brand_id}/models")
            self._models[key] = r.json() if r.status_code == 200 else []
        return self._models[key]

    async def lookup(
        self,
        brand: str,
        model: str,
        year: Optional[int],
        vtype_hint: str = "cars",
    ) -> Optional[float]:
        """Retorna o preço FIPE em float ou None se não encontrado."""
        cache_key = (_normalize(brand), _normalize(model), year, vtype_hint)
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        result = None
        order = [vtype_hint] + [t for t in VEHICLE_TYPES if t != vtype_hint]

        for vtype in order:
            brands = await self._brands_for(vtype)
            brand_match = _best_match(brand, [b["name"] for b in brands])
            if not brand_match:
                continue

            brand_id = next(b["code"] for b in brands if b["name"] == brand_match)
            models = await self._models_for(vtype, brand_id)
            model_match = _best_match(model, [m["name"] for m in models])
            if not model_match:
                continue

            model_id = next(m["code"] for m in models if m["name"] == model_match)

            r = await self._http.get(f"/{vtype}/brands/{brand_id}/models/{model_id}/years")
            years = r.json() if r.status_code == 200 else []
            year_id = _best_year_code(years, year)
            if not year_id:
                continue

            r2 = await self._http.get(
                f"/{vtype}/brands/{brand_id}/models/{model_id}/years/{year_id}"
            )
            if r2.status_code == 200:
                result = _parse_fipe_price(r2.json().get("price"))
                if result:
                    logger.debug(
                        "FIPE match: %s %s %s → R$ %.2f [%s]",
                        brand, model, year, result, vtype,
                    )
                    break

        self._price_cache[cache_key] = result
        return result