"""Validated market-data ingestion and immutable snapshot persistence."""
from .service import persist_market_snapshot
__all__ = ["persist_market_snapshot"]
