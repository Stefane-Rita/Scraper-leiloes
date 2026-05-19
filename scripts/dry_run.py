"""Executa scraping sem Google Sheets (teste local)."""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import collect_lots

logging.basicConfig(level=logging.INFO)


async def main():
    lots = await collect_lots()
    print(f"\nTotal: {len(lots)} lotes ATIVOS (veículos em leilão aberto)\n")
    for lot in lots[:5]:
        print(
            f"[{lot.fonte}] {lot.modelo_veiculo} | Lance: {lot.lance_atual} | "
            f"Avaliado: {lot.preco_avaliado} | Oportunidade: {lot.oportunidade}"
        )
    copart = sum(1 for l in lots if l.fonte == "Copart")
    sodre = sum(1 for l in lots if l.fonte == "Sodré Santoro")
    print(f"\nCopart: {copart} | Sodré: {sodre}")


if __name__ == "__main__":
    asyncio.run(main())
