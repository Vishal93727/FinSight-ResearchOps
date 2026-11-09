"""Isolated SQLite test database and seeded phase-one catalogue."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import DataProvider, Role


@pytest.fixture()
def db_session():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(test_engine)
    with TestingSession() as db:
        roles = [
            ("ADMIN", "Administrator"),
            ("RESEARCH_ANALYST", "Research Analyst"),
            ("QUANT_RESEARCHER", "Quant Researcher"),
            ("RISK_REVIEWER", "Risk Reviewer"),
            ("PORTFOLIO_ANALYST", "Portfolio Analyst"),
            ("READ_ONLY_VIEWER", "Read-only Viewer"),
        ]
        for key, name in roles:
            db.add(Role(key=key, name=name, description="test role"))
        db.add(DataProvider(key="manual_upload", display_name="Manual upload", provider_type="MARKET_DATA"))
        db.add(DataProvider(key="sec_edgar", display_name="SEC EDGAR", provider_type="FILINGS"))
        db.commit()
        yield db
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
