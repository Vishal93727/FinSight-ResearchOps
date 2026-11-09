"""Central SQLAlchemy model registry for metadata and backward-compatible imports."""
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id
from finsight.identity.models import Role, User, user_roles  # noqa: F401
from finsight.market_data.models import DataProvider, DataSnapshot, Instrument, SECCompanyRecord  # noqa: F401
from finsight.research.hypotheses.models import ResearchHypothesis  # noqa: F401
from finsight.features.models import FeatureSetVersion  # noqa: F401
from finsight.experiments.models import Experiment, ExperimentRun  # noqa: F401
from finsight.risk.models import ExperimentRiskReview  # noqa: F401
from finsight.documents.models import ResearchDocument, DocumentChunk, ResearchReport, ModelEvaluation, ResearchWorkflowCheckpoint  # noqa: F401
from finsight.governance.models import ModelVersion, ModelRiskReview, ModelGovernanceDecision, RLPolicyEvaluation  # noqa: F401
from finsight.execution.models import PaperAccount, PaperOrder, PaperFill, PaperPosition, PaperLedgerEntry  # noqa: F401
from finsight.feedback.models import PredictionOutcome, DriftAssessment, ResearchSuggestion, StrategyPerformanceSnapshot  # noqa: F401


class JobRecord(Base):
    __tablename__ = "job_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_job_owner_idempotency", "created_by", "idempotency_key", unique=True),)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

__all__ = ["Base", "User", "Role", "Instrument", "DataProvider", "DataSnapshot", "SECCompanyRecord", "JobRecord", "AuditEvent", "ResearchHypothesis", "FeatureSetVersion", "Experiment", "ExperimentRun", "ExperimentRiskReview", "ResearchDocument", "DocumentChunk", "ResearchReport", "ModelEvaluation", "ResearchWorkflowCheckpoint", "ModelVersion", "ModelRiskReview", "ModelGovernanceDecision", "RLPolicyEvaluation", "PaperAccount", "PaperOrder", "PaperFill", "PaperPosition", "PaperLedgerEntry", "PredictionOutcome", "DriftAssessment", "StrategyPerformanceSnapshot", "ResearchSuggestion", "user_roles", "new_id"]
