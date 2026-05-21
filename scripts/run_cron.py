import logging
import sys
from dotenv import load_dotenv
from src.pipeline import run_pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cron")

if __name__ == "__main__":
    logger.info("=== Iniciando pipeline (cron job) ===")
    try:
        count = run_pipeline()
        logger.info("Pipeline concluído: %d lotes sincronizados", count)
        sys.exit(0)
    except Exception as exc:
        logger.exception("Pipeline falhou: %s", exc)
        sys.exit(1)