"""Add claim-support records, durable workflow checkpoints and optional pgvector index.

Revision ID: 0006_phase3_evidence_vector_checkpoints
Revises: 0005_phase3_document_ai_ml
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_phase3_evidence_vector_checkpoints"
down_revision = "0005_phase3_document_ai_ml"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_reports", sa.Column("claim_checks", sa.JSON(), nullable=False,
        server_default=sa.text("'{}'")))
    op.create_table(
        "research_workflow_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("node", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("state_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "sequence", name="uq_research_checkpoint_sequence"),
    )
    op.create_index("ix_research_workflow_checkpoints_workflow_id", "research_workflow_checkpoints", ["workflow_id"])
    op.create_index("ix_research_checkpoint_workflow_created", "research_workflow_checkpoints", ["workflow_id", "created_at"])

    # The production Compose database uses pgvector/pgvector. SQLite and other test
    # dialects keep the JSON vector column and skip the Postgres-only ANN index.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE document_chunks ADD COLUMN embedding_vector vector(384)")
        op.execute(
            "CREATE INDEX ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding_vector vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64) WHERE embedding_vector IS NOT NULL"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
        op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding_vector")
    op.drop_index("ix_research_checkpoint_workflow_created", table_name="research_workflow_checkpoints")
    op.drop_index("ix_research_workflow_checkpoints_workflow_id", table_name="research_workflow_checkpoints")
    op.drop_table("research_workflow_checkpoints")
    op.drop_column("research_reports", "claim_checks")
