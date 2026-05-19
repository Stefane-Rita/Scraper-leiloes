"""Filtros para manter apenas veículos em leilões ativos."""
from datetime import datetime
from typing import Any, Optional

# Sodré: IDs de status encerrado / cancelado / arrematado
SODRE_INACTIVE_LOT_STATUS_IDS = {5, 6, 7}
SODRE_ACTIVE_AUCTION_STATUSES = {"aberto", "online"}
SODRE_ACTIVE_LOT_STATUS = "andamento"

# Copart: ss=0 costuma indicar lote em leilão aberto na listagem pública
COPART_ACTIVE_SALE_STATUS = {0}


def _parse_dt(value: str) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    text = str(value).replace("T", " ").strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _not_ended(end_date: str) -> bool:
    """True se não há data de fim ou o fim ainda não passou."""
    parsed = _parse_dt(end_date)
    if parsed is None:
        return True
    return parsed >= datetime.now()


def is_active_sodre_lot(item: dict[str, Any]) -> bool:
    if str(item.get("segment_id")) != "1" and item.get("segment_slug") != "veiculos":
        return False

    auction_status = (item.get("auction_status") or "").lower()
    if auction_status not in SODRE_ACTIVE_AUCTION_STATUSES:
        return False

    lot_status = (item.get("lot_status") or "").lower()
    if lot_status != SODRE_ACTIVE_LOT_STATUS:
        return False

    status_id = item.get("lot_status_id")
    if status_id is not None and int(status_id) in SODRE_INACTIVE_LOT_STATUS_IDS:
        return False

    if item.get("lot_test") is True:
        return False

    end = item.get("lot_date_end") or item.get("auction_date_end") or ""
    if not _not_ended(end):
        return False

    return True


def is_active_copart_lot(item: dict[str, Any]) -> bool:
    sale_type = (item.get("saleType") or "").lower()
    if "leil" not in sale_type:
        return False

    if item.get("offFlg") is True:
        return False

    ss = item.get("ss")
    if ss is not None and ss not in COPART_ACTIVE_SALE_STATUS:
        return False

    # Lotes sem data de leilão e sem lance costumam ser cadastros inativos na listagem
    ad = (item.get("ad") or "").strip()
    hb = float(item.get("hb") or 0)
    la = float(item.get("la") or 0) if item.get("la") not in (None, "") else 0.0
    if not ad and hb <= 0 and la <= 0:
        return False

    return True
