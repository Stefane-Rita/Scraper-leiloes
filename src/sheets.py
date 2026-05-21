import json
import logging
import os
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from src.models import HEADERS, AuctionLot

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Required keys that must be present in a valid service-account JSON
_REQUIRED_CREDENTIAL_KEYS = {"type", "project_id", "private_key", "client_email"}


def _load_credentials_info() -> dict:
    """Carrega credenciais do JSON em variável de ambiente ou arquivo."""
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if creds_json:
        try:
            info = json.loads(creds_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "GOOGLE_SHEETS_CREDENTIALS_JSON contém JSON inválido: "
                f"{exc}"
            ) from exc
        _validate_credentials_info(info, source="GOOGLE_SHEETS_CREDENTIALS_JSON")
        return info

    creds_file = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE")
    if creds_file:
        path = Path(creds_file)
        if not path.is_file():
            raise ValueError(f"Arquivo de credenciais não encontrado: {path}")
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Arquivo de credenciais '{path}' contém JSON inválido: {exc}"
            ) from exc
        _validate_credentials_info(info, source=str(path))
        return info

    raise ValueError(
        "Configure GOOGLE_SHEETS_CREDENTIALS_JSON (conteúdo do JSON) "
        "ou GOOGLE_SHEETS_CREDENTIALS_FILE (caminho do arquivo .json)"
    )


def _validate_credentials_info(info: dict, source: str) -> None:
    """Verifica que o dicionário de credenciais possui os campos obrigatórios."""
    missing = _REQUIRED_CREDENTIAL_KEYS - info.keys()
    if missing:
        raise ValueError(
            f"Credenciais inválidas em '{source}': campos ausentes: "
            f"{', '.join(sorted(missing))}"
        )
    if info.get("type") != "service_account":
        raise ValueError(
            f"Credenciais em '{source}' não são do tipo 'service_account' "
            f"(encontrado: '{info.get('type')}')"
        )
    logger.debug(
        "Credenciais validadas para conta de serviço: %s", info.get("client_email")
    )


def _sync_retry(max_attempts: int = 3, delay: float = 2.0):
    """Decorator de retry síncrono para métodos de SheetsClient."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts:
                        logger.error(
                            "Sheets: todas as %s tentativas falharam em '%s': %s",
                            max_attempts,
                            func.__name__,
                            exc,
                        )
                        raise
                    logger.warning(
                        "Sheets: tentativa %s/%s falhou em '%s': %s. "
                        "Aguardando %.1fs antes de tentar novamente...",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
        return wrapper
    return decorator


class SheetsClient:
    def __init__(self):
        spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID")
        if not spreadsheet_id:
            raise ValueError("GOOGLE_SPREADSHEET_ID não configurado")
        logger.debug("Usando planilha ID: %s", spreadsheet_id)

        info = _load_credentials_info()
        try:
            credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as exc:
            raise ValueError(
                f"Falha ao criar credenciais Google a partir do JSON fornecido: {exc}"
            ) from exc

        self._service_email = info.get("client_email", "")
        logger.info("Autenticando como conta de serviço: %s", self._service_email)

        try:
            client = client = gspread.service_account_from_dict(info)
            spreadsheet = client.open_by_key(spreadsheet_id)
        except Exception as exc:
            raise ValueError(
                f"Não foi possível abrir a planilha '{spreadsheet_id}': {exc}. "
                "Verifique se o ID está correto e se a conta de serviço tem acesso."
            ) from exc

        worksheet_name = os.getenv("GOOGLE_WORKSHEET_NAME", "Leilões")
        try:
            self._sheet = spreadsheet.worksheet(worksheet_name)
            logger.debug("Aba '%s' encontrada", worksheet_name)
        except gspread.WorksheetNotFound:
            logger.info("Aba '%s' não existe; criando...", worksheet_name)
            self._sheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=1000, cols=len(HEADERS)
            )

    @property
    def service_account_email(self) -> str:
        return self._service_email

    @_sync_retry(max_attempts=3, delay=2.0)
    def sync(self, lots: list[AuctionLot]) -> None:
        if not lots:
            logger.warning(
                "Sheets.sync chamado com lista vazia — planilha será limpa mas sem lotes"
            )
        now = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")
        meta_row = [f"Última atualização: {now} | Total de lotes ativos: {len(lots)}"]
        rows = [meta_row, HEADERS] + [lot.to_row() for lot in lots]

        logger.info(
            "Sincronizando %s lotes com a planilha (%s linhas no total)...",
            len(lots),
            len(rows),
        )
        self._sheet.clear()
        self._sheet.update(rows, "A1", value_input_option="USER_ENTERED")
        logger.info("Planilha atualizada com %s lotes", len(lots))
