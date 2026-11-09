"""Optional live PostgreSQL/Redis readiness test enabled in CI integration job."""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.skipif(
    os.getenv("FINSIGHT_RUN_LIVE_CHECKS") != "1",
    reason="Set FINSIGHT_RUN_LIVE_CHECKS=1 when PostgreSQL and Redis are available",
)
def test_live_database_and_redis_readiness() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {"database": "ok", "redis": "ok"}
