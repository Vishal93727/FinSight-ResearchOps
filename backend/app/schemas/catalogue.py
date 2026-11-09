"""Financial instrument and provider schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class InstrumentCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9.\-^]+$")
    name: str = Field(min_length=1, max_length=200)
    exchange: str = Field(default="NASDAQ", max_length=32)
    asset_type: str = Field(default="EQUITY", pattern=r"^(EQUITY|ETF)$")
    currency: str = Field(default="USD", max_length=8)


class InstrumentResponse(ORMModel):
    id: str
    symbol: str
    name: str
    exchange: str
    asset_type: str
    currency: str
    is_active: bool
    created_at: datetime


class ProviderResponse(ORMModel):
    key: str
    display_name: str
    provider_type: str
    is_enabled: bool
