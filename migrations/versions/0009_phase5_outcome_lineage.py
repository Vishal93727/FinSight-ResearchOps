"""Add outcome idempotency and persisted strategy performance snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0009_phase5_outcome_lineage"
down_revision = "0008_phase5_feedback_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prediction_outcomes", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_index("uq_prediction_outcome_owner_idempotency", "prediction_outcomes", ["created_by", "idempotency_key"], unique=True)
    op.add_column("research_suggestions", sa.Column("dedupe_key", sa.String(64), nullable=True))
    op.create_index("uq_research_suggestion_owner_dedupe", "research_suggestions", ["created_by", "dedupe_key"], unique=True)
    op.create_table(
        "strategy_performance_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("strategy_key", sa.String(120), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("source_reference", sa.String(500)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_strategy_performance_snapshots_strategy_key", "strategy_performance_snapshots", ["strategy_key"])
    op.create_index("ix_strategy_performance_strategy_created", "strategy_performance_snapshots", ["strategy_key", "created_at"])
    op.create_index("ix_strategy_performance_snapshots_created_by", "strategy_performance_snapshots", ["created_by"])


def downgrade() -> None:
    op.drop_table("strategy_performance_snapshots")
    op.drop_index("uq_research_suggestion_owner_dedupe", table_name="research_suggestions")
    op.drop_column("research_suggestions", "dedupe_key")
    op.drop_index("uq_prediction_outcome_owner_idempotency", table_name="prediction_outcomes")
    op.drop_column("prediction_outcomes", "idempotency_key")
