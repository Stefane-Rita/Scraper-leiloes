"""
Valida a conexão com o Google Planilhas (sem rodar o scraper).

Uso:
  1. Configure o .env (veja docs/CONFIGURACAO_PLANILHA.md)
  2. python scripts/verificar_planilha.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


def main():
    from src.sheets import SheetsClient

    print("Verificando credenciais e acesso à planilha...\n")
    client = SheetsClient()
    print("OK — Conexão estabelecida.")
    print(f"\nCompartilhe a planilha com este e-mail (se ainda não fez):")
    print(f"  → {client.service_account_email}")
    print("\nEscrevendo linha de teste na planilha...")
    client._sheet.update(
        [["Teste OK — pode apagar esta linha. O scraper sobrescreve a aba a cada execução."]],
        "A1",
    )
    print("\nPronto! Execute: python scripts/sync_once.py")


if __name__ == "__main__":
    main()
