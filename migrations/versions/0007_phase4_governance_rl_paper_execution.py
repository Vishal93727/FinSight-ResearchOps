"""Add model governance, RL evaluations and paper-only execution ledger.

Revision ID: 0007_phase4_governance_rl_paper_execution
Revises: 0006_phase3_evidence_vector_checkpoints
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_phase4_governance_rl_paper_execution"
down_revision = "0006_phase3_evidence_vector_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rl_policy_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("algorithm", sa.String(16), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(36), sa.ForeignKey("data_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("feature_set_version_id", sa.String(36), sa.ForeignKey("feature_set_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("configuration_sha256", sa.String(64), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("artifact_uri", sa.String(1000)),
        sa.Column("artifact_sha256", sa.String(64)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("out_of_sample", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rl_policy_evaluations_algorithm", "rl_policy_evaluations", ["algorithm"])
    op.create_index("ix_rl_policy_evaluations_dataset_snapshot_id", "rl_policy_evaluations", ["dataset_snapshot_id"])
    op.create_index("ix_rl_policy_evaluations_feature_set_version_id", "rl_policy_evaluations", ["feature_set_version_id"])
    op.create_index("ix_rl_policy_evaluations_configuration_sha256", "rl_policy_evaluations", ["configuration_sha256"])
    op.create_index("ix_rl_policy_evaluations_status", "rl_policy_evaluations", ["status"])
    op.create_index("ix_rl_policy_evaluations_created_by", "rl_policy_evaluations", ["created_by"])

    op.create_table(
        "model_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_key", sa.String(120), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("model_family", sa.String(48), nullable=False),
        sa.Column("source_evaluation_id", sa.String(36), sa.ForeignKey("model_evaluations.id", ondelete="RESTRICT")),
        sa.Column("source_rl_evaluation_id", sa.String(36), sa.ForeignKey("rl_policy_evaluations.id", ondelete="RESTRICT")),
        sa.Column("artifact_uri", sa.String(1000)),
        sa.Column("artifact_sha256", sa.String(64)),
        sa.Column("dataset_snapshot_id", sa.String(36), sa.ForeignKey("data_snapshots.id", ondelete="RESTRICT")),
        sa.Column("feature_set_version_id", sa.String(36), sa.ForeignKey("feature_set_versions.id", ondelete="RESTRICT")),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("risk_decision", sa.String(16), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("model_key", "version", name="uq_model_version_key_version"),
    )
    for column in ("model_key", "model_family", "source_evaluation_id", "source_rl_evaluation_id",
                   "dataset_snapshot_id", "feature_set_version_id", "risk_decision", "state"):
        op.create_index(f"ix_model_versions_{column}", "model_versions", [column])
    op.create_index("ix_model_version_key_state", "model_versions", ["model_key", "state"])

    op.create_table(
        "model_risk_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(48), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("observed_metrics", sa.JSON(), nullable=False),
        sa.Column("breaches", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_risk_reviews_model_version_id", "model_risk_reviews", ["model_version_id"])
    op.create_index("ix_model_risk_reviews_decision", "model_risk_reviews", ["decision"])

    op.create_table(
        "model_governance_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_governance_decisions_model_version_id", "model_governance_decisions", ["model_version_id"])
    op.create_index("ix_model_governance_decisions_reviewer_user_id", "model_governance_decisions", ["reviewer_user_id"])
    op.create_index("ix_model_governance_decisions_decision", "model_governance_decisions", ["decision"])
    op.create_index("ix_model_governance_decision_created", "model_governance_decisions", ["model_version_id", "created_at"])

    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("initial_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("cash_balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("max_gross_exposure", sa.Float(), nullable=False),
        sa.Column("max_symbol_exposure", sa.Float(), nullable=False),
        sa.Column("max_order_notional", sa.Numeric(24, 8), nullable=False),
        sa.Column("fee_bps", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("kill_switch", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_paper_accounts_kill_switch", "paper_accounts", ["kill_switch"])
    op.create_index("ix_paper_accounts_created_by", "paper_accounts", ["created_by"])

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("simulation_reference_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("fill_price", sa.Numeric(24, 8)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("client_order_id", sa.String(128), nullable=False),
        sa.Column("risk_check", sa.JSON(), nullable=False),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("account_id", "client_order_id", name="uq_paper_order_client_id"),
    )
    op.create_index("ix_paper_orders_account_id", "paper_orders", ["account_id"])
    op.create_index("ix_paper_orders_model_version_id", "paper_orders", ["model_version_id"])
    op.create_index("ix_paper_orders_symbol", "paper_orders", ["symbol"])
    op.create_index("ix_paper_orders_status", "paper_orders", ["status"])
    op.create_index("ix_paper_order_account_created", "paper_orders", ["account_id", "created_at"])

    op.create_table(
        "paper_fills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("paper_orders.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("fill_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("fee_amount", sa.Numeric(24, 8), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_paper_fills_order_id", "paper_fills", ["order_id"])
    op.create_index("ix_paper_fills_account_id", "paper_fills", ["account_id"])
    op.create_index("ix_paper_fills_symbol", "paper_fills", ["symbol"])

    op.create_table(
        "paper_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("mark_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "symbol", name="uq_paper_position_account_symbol"),
    )
    op.create_index("ix_paper_positions_account_id", "paper_positions", ["account_id"])
    op.create_index("ix_paper_positions_symbol", "paper_positions", ["symbol"])

    op.create_table(
        "paper_ledger_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fill_id", sa.String(36), sa.ForeignKey("paper_fills.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("cash_delta", sa.Numeric(24, 8), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(24, 8), nullable=False),
        sa.Column("execution_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("entry_type", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_paper_ledger_entries_account_id", "paper_ledger_entries", ["account_id"])
    op.create_index("ix_paper_ledger_entries_fill_id", "paper_ledger_entries", ["fill_id"])
    op.create_index("ix_paper_ledger_entries_symbol", "paper_ledger_entries", ["symbol"])


def downgrade() -> None:
    for table, indexes in [
        ("paper_ledger_entries", ["ix_paper_ledger_entries_symbol", "ix_paper_ledger_entries_fill_id", "ix_paper_ledger_entries_account_id"]),
        ("paper_positions", ["ix_paper_positions_symbol", "ix_paper_positions_account_id"]),
        ("paper_fills", ["ix_paper_fills_symbol", "ix_paper_fills_account_id", "ix_paper_fills_order_id"]),
        ("paper_orders", ["ix_paper_order_account_created", "ix_paper_orders_status", "ix_paper_orders_symbol", "ix_paper_orders_model_version_id", "ix_paper_orders_account_id"]),
        ("paper_accounts", ["ix_paper_accounts_created_by", "ix_paper_accounts_kill_switch"]),
        ("model_governance_decisions", ["ix_model_governance_decision_created", "ix_model_governance_decisions_decision", "ix_model_governance_decisions_reviewer_user_id", "ix_model_governance_decisions_model_version_id"]),
        ("model_risk_reviews", ["ix_model_risk_reviews_decision", "ix_model_risk_reviews_model_version_id"]),
        ("model_versions", ["ix_model_version_key_state", "ix_model_versions_state", "ix_model_versions_risk_decision", "ix_model_versions_feature_set_version_id", "ix_model_versions_dataset_snapshot_id", "ix_model_versions_source_rl_evaluation_id", "ix_model_versions_source_evaluation_id", "ix_model_versions_model_family", "ix_model_versions_model_key"]),
        ("rl_policy_evaluations", ["ix_rl_policy_evaluations_created_by", "ix_rl_policy_evaluations_status", "ix_rl_policy_evaluations_configuration_sha256", "ix_rl_policy_evaluations_feature_set_version_id", "ix_rl_policy_evaluations_dataset_snapshot_id", "ix_rl_policy_evaluations_algorithm"]),
    ]:
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
