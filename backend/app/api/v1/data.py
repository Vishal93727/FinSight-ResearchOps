"""Financial data ingestion and immutable dataset snapshot endpoints."""

import hashlib
import json
from io import BytesIO
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight.market_data.providers.sec_edgar import SECEdgarClient
from finsight.core.config import get_settings
from finsight.core.security import get_current_user, require_roles
from finsight.infrastructure.database.session import get_db
from finsight.market_data.models import DataProvider, DataSnapshot, Instrument, SECCompanyRecord
from finsight.identity.models import User
from finsight.market_data.contracts.ingestion import MarketBar, MarketIngestionRequest, SECIngestionResponse, SnapshotResponse
from app.services.audit import record_audit
from finsight.market_data.ingestion.service import persist_market_snapshot

router = APIRouter(prefix="/data", tags=["financial data"])


@router.post("/ingestions/market", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
def ingest_market_bars(
    payload: MarketIngestionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER")),
) -> DataSnapshot:
    symbol = payload.symbol.upper()
    instrument = db.scalar(select(Instrument).where(Instrument.symbol == symbol, Instrument.is_active.is_(True)))
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument is not in the catalogue")
    provider = db.scalar(
        select(DataProvider).where(DataProvider.key == payload.provider_key, DataProvider.is_enabled.is_(True))
    )
    if provider is None or provider.provider_type != "MARKET_DATA" or provider.key != "manual_upload":
        raise HTTPException(status_code=422, detail="An enabled market-data provider is required")
    file_path, sha256, manifest, content_id = persist_market_snapshot(
        symbol=symbol,
        provider_key=payload.provider_key,
        interval=payload.interval,
        adjustment_policy=payload.adjustment_policy,
        rows=payload.rows,
    )
    snapshot = DataSnapshot(
        provider_key=payload.provider_key,
        instrument_symbol=symbol,
        interval=payload.interval,
        start_date=min(row.date for row in payload.rows),
        end_date=max(row.date for row in payload.rows),
        status="READY",
        file_path=file_path,
        storage_format="parquet",
        sha256=sha256,
        row_count=len(payload.rows),
        manifest=manifest | {"content_id": content_id},
        created_by=user.id,
    )
    db.add(snapshot)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="data.market_snapshot_created",
        resource_type="data_snapshot",
        resource_id=snapshot.id,
        request_id=getattr(request.state, "request_id", None),
        details={"symbol": symbol, "rows": len(payload.rows), "sha256": sha256},
    )
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.post("/ingestions/market/csv", response_model=SnapshotResponse, status_code=status.HTTP_201_CREATED)
async def ingest_market_csv(
    request: Request,
    symbol: str = Form(..., min_length=1, max_length=32),
    interval: str = Form("1d", pattern=r"^(1d|1h|1m)$"),
    adjustment_policy: str = Form("provider_defined", max_length=80),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER")),
) -> DataSnapshot:
    """Validate a CSV upload and create the same immutable snapshot as the JSON ingestion API."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a .csv file")
    raw = await file.read(15 * 1024 * 1024 + 1)
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 15 MB upload limit")
    try:
        frame = pd.read_csv(BytesIO(raw))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="CSV could not be parsed") from exc
    required_columns = {"date", "open", "high", "low", "close", "volume"}
    if not required_columns.issubset(set(frame.columns)):
        missing = sorted(required_columns - set(frame.columns))
        raise HTTPException(status_code=422, detail=f"Missing CSV columns: {', '.join(missing)}")
    settings = get_settings()
    if frame.empty or len(frame) > settings.max_ingestion_rows:
        raise HTTPException(status_code=422, detail="CSV must contain rows within the configured ingestion limit")
    bars: list[MarketBar] = []
    try:
        for row in frame.loc[:, sorted(required_columns)].to_dict(orient="records"):
            bars.append(
                MarketBar(
                    date=pd.to_datetime(row["date"], errors="raise").date(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    except (ValueError, TypeError, KeyError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="CSV contains invalid date or OHLCV values") from exc
    try:
        payload = MarketIngestionRequest(
            symbol=symbol.upper(),
            provider_key="manual_upload",
            interval=interval,
            adjustment_policy=adjustment_policy,
            rows=bars,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="CSV contains invalid market data") from exc
    # Reuse the JSON ingestion endpoint's validation and persistence path.
    return ingest_market_bars(payload, request, db, user)


@router.get("/snapshots", response_model=list[SnapshotResponse])
def list_snapshots(
    symbol: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DataSnapshot]:
    query = select(DataSnapshot).order_by(DataSnapshot.created_at.desc())
    if symbol:
        query = query.where(DataSnapshot.instrument_symbol == symbol.upper())
    return list(db.scalars(query.limit(100)).all())


@router.post("/ingestions/sec/{cik}", response_model=SECIngestionResponse)
async def ingest_sec_company(
    cik: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER")),
) -> SECIngestionResponse:
    settings = get_settings()
    try:
        client = SECEdgarClient(settings.sec_edgar_user_agent)
        payload = await client.fetch_company_submissions(cik)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="SEC EDGAR request failed") from exc
    normalized_cik = cik.strip().zfill(10)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(serialized).hexdigest()
    now = datetime.now(UTC)
    # Each successful fetch is appended as a new immutable record; prior hashes remain traceable.
    record = SECCompanyRecord(
        cik=normalized_cik,
        company_name=payload["name"],
        submissions_url=f"https://data.sec.gov/submissions/CIK{normalized_cik}.json",
        payload_sha256=digest,
        submissions=payload,
        ingested_at=now,
    )
    db.add(record)
    recent = payload.get("filings", {}).get("recent", {})
    filing_count = len(recent.get("accessionNumber", [])) if isinstance(recent, dict) else 0
    record_audit(
        db,
        actor=user,
        action="data.sec_submissions_ingested",
        resource_type="sec_company",
        resource_id=normalized_cik,
        request_id=getattr(request.state, "request_id", None),
        details={"company_name": payload["name"], "filings_count": filing_count, "sha256": digest},
    )
    db.commit()
    return SECIngestionResponse(
        cik=normalized_cik,
        company_name=payload["name"],
        payload_sha256=digest,
        ingested_at=now,
        filings_count=filing_count,
    )
