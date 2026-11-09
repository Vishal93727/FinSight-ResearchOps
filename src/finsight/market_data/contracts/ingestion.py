"""Market-data ingestion and snapshot schemas."""

from datetime import date, datetime
import math
from typing import Annotated

from pydantic import BaseModel, Field, model_validator


Positive = Annotated[float, Field(gt=0)]
NonNegative = Annotated[float, Field(ge=0)]


class MarketBar(BaseModel):
    date: date
    open: Positive
    high: Positive
    low: Positive
    close: Positive
    volume: NonNegative

    @model_validator(mode="after")
    def check_ohlc(self) -> "MarketBar":
        if not all(math.isfinite(value) for value in (self.open, self.high, self.low, self.close, self.volume)):
            raise ValueError("OHLCV values must be finite numbers")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be at least open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be at most open, close and high")
        return self


class MarketIngestionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.\-^]+$")
    provider_key: str = "manual_upload"
    interval: str = Field(default="1d", pattern=r"^(1d|1h|1m)$")
    adjustment_policy: str = Field(default="provider_defined", max_length=80)
    rows: list[MarketBar] = Field(min_length=1)


class SnapshotResponse(BaseModel):
    id: str
    provider_key: str
    instrument_symbol: str
    interval: str
    start_date: date
    end_date: date
    status: str
    storage_format: str
    sha256: str
    row_count: int
    manifest: dict
    created_at: datetime


class SECIngestionResponse(BaseModel):
    cik: str
    company_name: str
    payload_sha256: str
    ingested_at: datetime
    filings_count: int
