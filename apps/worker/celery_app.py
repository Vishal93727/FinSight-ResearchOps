"""Canonical worker entry point; delegates to the existing Celery application."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.workers.celery_app import celery_app  # noqa: E402

__all__ = ["celery_app"]
