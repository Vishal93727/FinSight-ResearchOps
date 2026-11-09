"""Validation and immutable snapshot storage for user-supplied market bars."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fastapi import HTTPException

from finsight.core.config import get_settings
from finsight.market_data.contracts.ingestion import MarketBar


def persist_market_snapshot(
    *, symbol: str, provider_key: str, interval: str, adjustment_policy: str, rows: list[MarketBar]
) -> tuple[str, str, dict, str]:
    settings = get_settings()
    if len(rows) > settings.max_ingestion_rows:
        raise HTTPException(status_code=413, detail="Ingestion exceeds the configured row limit")
    ordered = sorted(rows, key=lambda item: item.date)
    dates = [row.date for row in ordered]
    if len(set(dates)) != len(dates):
        raise HTTPException(status_code=422, detail="Duplicate market-data dates are not allowed")
    frame = pd.DataFrame([row.model_dump() for row in ordered])
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    # Preserve immutable content-addressed snapshots. PyArrow is a declared dependency.
    root = Path(settings.data_storage_path).resolve() / "raw" / "market"
    root.mkdir(parents=True, exist_ok=True)
    safe_symbol = re.sub(r"[^A-Za-z0-9_.-]", "_", symbol.upper())
    snapshot_id = hashlib.sha256(
        (safe_symbol + json.dumps([row.model_dump(mode="json") for row in ordered], sort_keys=True)).encode()
    ).hexdigest()
    target = root / f"{safe_symbol}-{snapshot_id[:16]}.parquet"
    if not target.exists():
        try:
            frame.to_parquet(target, index=False)
        except ImportError as exc:
            raise HTTPException(
                status_code=503, detail="Parquet support is unavailable; install project dependencies"
            ) from exc
    content_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest = {
        "snapshot_id": snapshot_id,
        "provider": provider_key,
        "instrument": safe_symbol,
        "start_date": dates[0].isoformat(),
        "end_date": dates[-1].isoformat(),
        "interval": interval,
        "timezone": "UTC",
        "adjustment_policy": adjustment_policy,
        "schema_version": "1.0",
        "row_count": len(ordered),
        "sha256": content_hash,
        "created_at": datetime.now(UTC).isoformat(),
        "provenance": "user_submitted_market_bars",
    }
    return str(target), content_hash, manifest, snapshot_id
