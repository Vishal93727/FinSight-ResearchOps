"""Paper-only accounts, orders, fills, positions and cash/quantity ledger."""
from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class PaperAccount(Base):
    __tablename__ = "paper_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    max_gross_exposure: Mapped[float] = mapped_column(default=1.0)
    max_symbol_exposure: Mapped[float] = mapped_column(default=0.40)
    max_order_notional: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("25000"))
    fee_bps: Mapped[float] = mapped_column(default=5.0)
    slippage_bps: Mapped[float] = mapped_column(default=5.0)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id", ondelete="RESTRICT"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    simulation_reference_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    client_order_id: Mapped[str] = mapped_column(String(128))
    risk_check: Mapped[dict] = mapped_column(JSON, default=dict)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("account_id", "client_order_id", name="uq_paper_order_client_id"),
                      Index("ix_paper_order_account_created", "account_id", "created_at"))


class PaperFill(Base):
    __tablename__ = "paper_fills"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("paper_orders.id", ondelete="CASCADE"), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    fill_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    slippage_bps: Mapped[float] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PaperPosition(Base):
    __tablename__ = "paper_positions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    mark_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_paper_position_account_symbol"),)


class PaperLedgerEntry(Base):
    __tablename__ = "paper_ledger_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True)
    fill_id: Mapped[str] = mapped_column(ForeignKey("paper_fills.id", ondelete="RESTRICT"), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    execution_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    entry_type: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
