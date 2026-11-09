"""Market-data catalogue, provider and immutable snapshot persistence models."""
from datetime import UTC, date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import TimestampMixin, new_id


class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    exchange: Mapped[str] = mapped_column(String(32), default="NASDAQ")
    asset_type: Mapped[str] = mapped_column(String(24), default="EQUITY")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DataProvider(TimestampMixin, Base):
    __tablename__ = "data_providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    provider_type: Mapped[str] = mapped_column(String(32))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class DataSnapshot(Base):
    __tablename__ = "data_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    instrument_symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8), default="1d")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="READY")
    file_path: Mapped[str] = mapped_column(Text)
    storage_format: Mapped[str] = mapped_column(String(16), default="parquet")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    row_count: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_snapshot_symbol_range", "instrument_symbol", "start_date", "end_date"),)


class SECCompanyRecord(Base):
    __tablename__ = "sec_company_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cik: Mapped[str] = mapped_column(String(10), index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    submissions_url: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    submissions: Mapped[dict] = mapped_column(JSON)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
