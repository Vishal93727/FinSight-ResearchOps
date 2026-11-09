"""Durable feedback, drift, strategy monitoring and research suggestion ledgers.

These ORM mappings intentionally match Alembic migrations 0008 and 0009.
"""
from datetime import UTC, date, datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class PredictionOutcome(Base):
    __tablename__ = "prediction_outcomes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    instrument_symbol: Mapped[str] = mapped_column(String(32), index=True)
    forecast_date: Mapped[date] = mapped_column(Date)
    realised_date: Mapped[date] = mapped_column(Date)
    horizon_sessions: Mapped[int] = mapped_column(default=1)
    predicted_return: Mapped[float] = mapped_column(Float)
    realised_return: Mapped[float] = mapped_column(Float)
    benchmark_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version_id: Mapped[str | None] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    experiment_run_id: Mapped[str | None] = mapped_column(ForeignKey("experiment_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    paper_account_id: Mapped[str | None] = mapped_column(ForeignKey("paper_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    observation_source: Mapped[str] = mapped_column(String(80))
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (
        UniqueConstraint("created_by", "idempotency_key", name="uq_prediction_outcome_owner_idempotency"),
        Index("ix_prediction_outcomes_model_realised", "model_version_id", "realised_date"),
    )


class DriftAssessment(Base):
    __tablename__ = "drift_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_version_id: Mapped[str | None] = mapped_column(ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    reference_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id", ondelete="SET NULL"), nullable=True)
    current_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id", ondelete="SET NULL"), nullable=True)
    overall_status: Mapped[str] = mapped_column(String(16), index=True)
    feature_results: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ResearchSuggestion(Base):
    __tablename__ = "research_suggestions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240))
    rationale: Mapped[str] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED", index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("created_by", "dedupe_key", name="uq_research_suggestion_owner_dedupe"),)


class StrategyPerformanceSnapshot(Base):
    __tablename__ = "strategy_performance_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    strategy_key: Mapped[str] = mapped_column(String(120), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_strategy_performance_strategy_created", "strategy_key", "created_at"),)
