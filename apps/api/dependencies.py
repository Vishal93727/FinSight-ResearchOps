"""Shared API dependency exports during the backend package migration."""
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from finsight.infrastructure.database.session import get_db  # noqa: E402

__all__ = ["get_db"]
