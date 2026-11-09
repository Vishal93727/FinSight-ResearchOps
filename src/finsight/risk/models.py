"""Persisted deterministic risk-review decisions for experiment runs."""
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class ExperimentRiskReview(Base):
    __tablename__ = "experiment_risk_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    policy_version: Mapped[str] = mapped_column(String(40))
    limits: Mapped[dict] = mapped_column(JSON)
    observed_metrics: Mapped[dict] = mapped_column(JSON)
    breaches: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    deterministic: Mapped[bool] = mapped_column(default=True)
    override_allowed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (UniqueConstraint("run_id", name="uq_experiment_risk_review_run"),
                      Index("ix_risk_review_decision_created", "decision", "created_at"))
