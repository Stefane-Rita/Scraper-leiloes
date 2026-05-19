"""Executa uma coleta completa e envia para o Google Planilhas (uma vez)."""
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO)


def main():
    from src.pipeline import run_pipeline

    total = run_pipeline()
    print(f"\nConcluído: {total} lotes ativos enviados à planilha.")


if __name__ == "__main__":
    main()
