"""Persistent document, chunk, research-report and ML-evaluation records."""
from datetime import UTC, datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class ResearchDocument(Base):
    __tablename__ = "research_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240))
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(32), default="UPLOAD")
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content_text: Mapped[str] = mapped_column(Text)
    character_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="READY", index=True)
    document_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_research_documents_created", "created_at"),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("research_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list] = mapped_column(JSON)
    token_count: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        Index("ix_document_chunks_document_index", "document_id", "chunk_index"),
    )


class ResearchReport(Base):
    __tablename__ = "research_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    query: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="AWAITING_REVIEW", index=True)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    workflow_trace: Mapped[list] = mapped_column(JSON, default=list)
    retrieval_config: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    claim_checks: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    reviewer_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_research_reports_status_created", "status", "created_at"),)


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.id", ondelete="RESTRICT"), index=True)
    instrument_symbol: Mapped[str] = mapped_column(String(32), index=True)
    feature_set_version_id: Mapped[str] = mapped_column(ForeignKey("feature_set_versions.id", ondelete="RESTRICT"), index=True)
    model_family: Mapped[str] = mapped_column(String(32))
    target_column: Mapped[str] = mapped_column(String(80))
    feature_columns: Mapped[list] = mapped_column(JSON)
    configuration: Mapped[dict] = mapped_column(JSON)
    configuration_sha256: Mapped[str] = mapped_column(String(64), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="SUCCEEDED", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ResearchWorkflowCheckpoint(Base):
    """Durable, bounded recovery state for each research workflow node."""
    __tablename__ = "research_workflow_checkpoints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (
        UniqueConstraint("workflow_id", "sequence", name="uq_research_checkpoint_sequence"),
        Index("ix_research_checkpoint_workflow_created", "workflow_id", "created_at"),
    )
