import logging
import os
import threading
import time

import schedule
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from src.pipeline import run_pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("webscraper")

app = FastAPI(title="Web Scraper Leilões")
_last_run: dict = {"status": "idle", "lots": 0, "error": None}


def _scheduled_job():
    global _last_run
    try:
        count = run_pipeline()
        _last_run = {"status": "ok", "lots": count, "error": None}
    except Exception as exc:
        logger.exception("Falha no pipeline")
        _last_run = {"status": "error", "lots": 0, "error": str(exc)}


def _scheduler_loop():
    interval = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "300"))
    schedule.every(interval).seconds.do(_scheduled_job)
    logger.info("Agendador iniciado (intervalo: %ss)", interval)
    _scheduled_job()
    while True:
        schedule.run_pending()
        time.sleep(1)


@app.get("/")
def health():
    return {"service": "web-scraper-leiloes", **_last_run}


@app.post("/run")
def run_now():
    threading.Thread(target=_scheduled_job, daemon=True).start()
    return {"message": "Execução iniciada em background"}


if __name__ == "__main__":
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
