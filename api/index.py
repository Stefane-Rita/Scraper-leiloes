"""
Entrada serverless da Vercel — expõe o app FastAPI definido em main.py.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app  # noqa: F401 — Vercel detecta `app` (ASGI)
