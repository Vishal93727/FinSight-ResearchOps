"""Persist research documents/chunks, evidence reports and supervised evaluations.

Revision ID: 0005_phase3_document_ai_ml
Revises: 0004_phase2_benchmark_risk_review
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_phase3_document_ai_ml"
down_revision = "0004_phase2_benchmark_risk_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.String(length=1000), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("document_metadata", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_documents_content_sha256", "research_documents", ["content_sha256"], unique=True)
    op.create_index("ix_research_documents_status", "research_documents", ["status"])
    op.create_index("ix_research_documents_created_by", "research_documents", ["created_by"])
    op.create_index("ix_research_documents_created", "research_documents", ["created_at"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["research_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_text_sha256", "document_chunks", ["text_sha256"])
    op.create_index("ix_document_chunks_document_index", "document_chunks", ["document_id", "chunk_index"])

    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("workflow_trace", sa.JSON(), nullable=False),
        sa.Column("retrieval_config", sa.JSON(), nullable=False),
        sa.Column("evidence_verified", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("reviewer_user_id", sa.String(length=36), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_reports_status", "research_reports", ["status"])
    op.create_index("ix_research_reports_created_by", "research_reports", ["created_by"])
    op.create_index("ix_research_reports_status_created", "research_reports", ["status", "created_at"])

    op.create_table(
        "model_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_symbol", sa.String(length=32), nullable=False),
        sa.Column("feature_set_version_id", sa.String(length=36), nullable=False),
        sa.Column("model_family", sa.String(length=32), nullable=False),
        sa.Column("target_column", sa.String(length=80), nullable=False),
        sa.Column("feature_columns", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("configuration_sha256", sa.String(length=64), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("artifact_path", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["data_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["feature_set_version_id"], ["feature_set_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_evaluations_dataset_snapshot_id", "model_evaluations", ["dataset_snapshot_id"])
    op.create_index("ix_model_evaluations_instrument_symbol", "model_evaluations", ["instrument_symbol"])
    op.create_index("ix_model_evaluations_feature_set_version_id", "model_evaluations", ["feature_set_version_id"])
    op.create_index("ix_model_evaluations_configuration_sha256", "model_evaluations", ["configuration_sha256"])
    op.create_index("ix_model_evaluations_status", "model_evaluations", ["status"])
    op.create_index("ix_model_evaluations_created_by", "model_evaluations", ["created_by"])


def downgrade() -> None:
    for name in ["ix_model_evaluations_created_by", "ix_model_evaluations_status",
                 "ix_model_evaluations_configuration_sha256", "ix_model_evaluations_feature_set_version_id", "ix_model_evaluations_instrument_symbol",
                 "ix_model_evaluations_dataset_snapshot_id"]:
        op.drop_index(name, table_name="model_evaluations")
    op.drop_table("model_evaluations")
    op.drop_index("ix_research_reports_status_created", table_name="research_reports")
    op.drop_index("ix_research_reports_created_by", table_name="research_reports")
    op.drop_index("ix_research_reports_status", table_name="research_reports")
    op.drop_table("research_reports")
    op.drop_index("ix_document_chunks_document_index", table_name="document_chunks")
    op.drop_index("ix_document_chunks_text_sha256", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_research_documents_created", table_name="research_documents")
    op.drop_index("ix_research_documents_created_by", table_name="research_documents")
    op.drop_index("ix_research_documents_status", table_name="research_documents")
    op.drop_index("ix_research_documents_content_sha256", table_name="research_documents")
    op.drop_table("research_documents")
