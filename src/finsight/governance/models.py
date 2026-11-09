"""Immutable model versions, independent risk reviews and human governance decisions."""
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(64))
    model_family: Mapped[str] = mapped_column(String(48), index=True)
    source_evaluation_id: Mapped[str | None] = mapped_column(ForeignKey("model_evaluations.id", ondelete="RESTRICT"), nullable=True, index=True)
    source_rl_evaluation_id: Mapped[str | None] = mapped_column(ForeignKey("rl_policy_evaluations.id", ondelete="RESTRICT"), nullable=True, index=True)
    artifact_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dataset_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("data_snapshots.id", ondelete="RESTRICT"), nullable=True, index=True)
    feature_set_version_id: Mapped[str | None] = mapped_column(ForeignKey("feature_set_versions.id", ondelete="RESTRICT"), nullable=True, index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_decision: Mapped[str] = mapped_column(String(16), default="REVIEW", index=True)
    state: Mapped[str] = mapped_column(String(24), default="CANDIDATE", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    __table_args__ = (UniqueConstraint("model_key", "version", name="uq_model_version_key_version"),
                      Index("ix_model_version_key_state", "model_key", "state"))


class ModelRiskReview(Base):
    __tablename__ = "model_risk_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"), unique=True, index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    policy_version: Mapped[str] = mapped_column(String(48))
    limits: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    breaches: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    deterministic: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ModelGovernanceDecision(Base):
    __tablename__ = "model_governance_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"), index=True)
    reviewer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decision: Mapped[str] = mapped_column(String(16), index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_model_governance_decision_created", "model_version_id", "created_at"),)


class RLPolicyEvaluation(Base):
    __tablename__ = "rl_policy_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    algorithm: Mapped[str] = mapped_column(String(16), index=True)
    dataset_snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.id", ondelete="RESTRICT"), index=True)
    feature_set_version_id: Mapped[str] = mapped_column(ForeignKey("feature_set_versions.id", ondelete="RESTRICT"), index=True)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_sha256: Mapped[str] = mapped_column(String(64), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="SUCCEEDED", index=True)
    out_of_sample: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
