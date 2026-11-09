"""Initial FinSight ResearchOps identity, catalogue, snapshot and audit schema.

Revision ID: 0001_initial_researchops
Revises:
"""

from uuid import uuid4

from alembic import op
from sqlalchemy import insert

from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.models import DataProvider, Role  # noqa: F401
from finsight.infrastructure.database import models  # noqa: F401 - register metadata

revision = "0001_initial_researchops"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    initial_tables = ["user_roles", "users", "roles", "instruments", "data_providers",
                      "data_snapshots", "sec_company_records", "job_records", "audit_events"]
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[name] for name in initial_tables])
    roles = [
        ("ADMIN", "Administrator", "Platform configuration and user/role administration."),
        ("RESEARCH_ANALYST", "Research Analyst", "Research documents, companies and hypotheses."),
        ("QUANT_RESEARCHER", "Quant Researcher", "Features, experiments, training and backtests."),
        ("RISK_REVIEWER", "Risk Reviewer", "Risk review, approval and suspension decisions."),
        ("PORTFOLIO_ANALYST", "Portfolio Analyst", "Paper positions, fills and performance."),
        ("READ_ONLY_VIEWER", "Read-only Viewer", "Approved reports and permitted dashboards."),
    ]
    for key, name, description in roles:
        bind.execute(
            insert(Role).values(id=str(uuid4()), key=key, name=name, description=description)
        )
    providers = [
        ("manual_upload", "User-supplied market bars", "MARKET_DATA"),
        ("sec_edgar", "SEC EDGAR submissions", "FILINGS"),
    ]
    for key, name, provider_type in providers:
        bind.execute(
            insert(DataProvider).values(
                id=str(uuid4()), key=key, display_name=name, provider_type=provider_type,
                is_enabled=True, config={}
            )
        )


def downgrade() -> None:
    initial_tables = ["audit_events", "job_records", "sec_company_records", "data_snapshots",
                      "data_providers", "instruments", "user_roles", "users", "roles"]
    Base.metadata.drop_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in initial_tables])
