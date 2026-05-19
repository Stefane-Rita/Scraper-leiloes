import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from src.models import HEADERS, AuctionLot

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _load_credentials_info() -> dict:
    """Carrega credenciais do JSON em variável de ambiente ou arquivo."""
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if creds_json:
        return json.loads(creds_json)

    creds_file = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE")
    if creds_file:
        path = Path(creds_file)
        if not path.is_file():
            raise ValueError(f"Arquivo de credenciais não encontrado: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    raise ValueError(
        "Configure GOOGLE_SHEETS_CREDENTIALS_JSON (conteúdo do JSON) "
        "ou GOOGLE_SHEETS_CREDENTIALS_FILE (caminho do arquivo .json)"
    )


class SheetsClient:
    def __init__(self):
        spreadsheet_id = os.environ.get("GOOGLE_SPREADSHEET_ID")
        if not spreadsheet_id:
            raise ValueError("GOOGLE_SPREADSHEET_ID não configurado")

        info = _load_credentials_info()
        credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
        self._service_email = info.get("client_email", "")
        client = gspread.authorize(credentials)

        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet_name = os.getenv("GOOGLE_WORKSHEET_NAME", "Leilões")
        try:
            self._sheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            logger.info("Aba '%s' não existe; criando...", worksheet_name)
            self._sheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=1000, cols=len(HEADERS)
            )

    @property
    def service_account_email(self) -> str:
        return self._service_email

    def sync(self, lots: list[AuctionLot]) -> None:
        now = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")
        meta_row = [f"Última atualização: {now} | Total de lotes ativos: {len(lots)}"]
        rows = [meta_row, HEADERS] + [lot.to_row() for lot in lots]

        self._sheet.clear()
        self._sheet.update(rows, "A1", value_input_option="USER_ENTERED")
        logger.info("Planilha atualizada com %s lotes", len(lots))
