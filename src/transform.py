import re
from typing import Optional

APPRAISAL_PATTERN = re.compile(
    r"avalia[cç][aã]o\s*:\s*r\$\s*([\d.,]+)",
    re.IGNORECASE,
)


def parse_brl(value) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def extract_appraisal_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    match = APPRAISAL_PATTERN.search(text)
    if not match:
        return None
    return parse_brl(match.group(1))


def calc_diff(lance: Optional[float], avaliado: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if lance is None or avaliado is None or avaliado <= 0:
        return None, None
    diff_rs = avaliado - lance
    diff_pct = (lance / avaliado) * 100
    return diff_rs, diff_pct


def is_opportunity(lance: Optional[float], avaliado: Optional[float], threshold: float = 0.45) -> str:
    if lance is None or avaliado is None or avaliado <= 0:
        return "Indisponível"
    if lance <= avaliado * threshold:
        return "Sim"
    return "Não"


def format_datetime_br(value: str) -> str:
    if not value:
        return ""
    return value.replace("T", " ").strip()[:19]
