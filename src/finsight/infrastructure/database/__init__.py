"""Database infrastructure with lazy runtime-engine imports.

Alembic and metadata tooling must be able to import ``Base`` without creating a
live engine or importing a PostgreSQL DBAPI driver. Runtime session symbols remain
available through lazy attribute access for backwards compatibility.
"""
from __future__ import annotations

from .base import Base

__all__ = ["Base", "SessionLocal", "engine", "get_db"]


def __getattr__(name: str):
    if name in {"SessionLocal", "engine", "get_db"}:
        from . import session
        return getattr(session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
