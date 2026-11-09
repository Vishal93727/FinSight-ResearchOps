"""Reproducible experiment specifications and execution records."""
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(180))
    hypothesis_id: Mapped[str] = mapped_column(ForeignKey("research_hypotheses.id", ondelete="RESTRICT"), index=True)
    instrument_symbol: Mapped[str] = mapped_column(String(32), index=True)
    dataset_snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.id", ondelete="RESTRICT"), index=True)
    benchmark_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id", ondelete="RESTRICT", name="fk_experiments_benchmark_snapshot_id_data_snapshots"), nullable=True, index=True)
    feature_set_version_id: Mapped[str] = mapped_column(ForeignKey("feature_set_versions.id", ondelete="RESTRICT"), index=True)
    configuration: Mapped[dict] = mapped_column(JSON)
    configuration_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_experiment_symbol_status", "instrument_symbol", "status"),)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    run_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    random_seed: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (
        UniqueConstraint("experiment_id", "run_number", name="uq_experiment_run_number"),
        Index("uq_experiment_run_idempotency", "experiment_id", "idempotency_key", unique=True),
    )
