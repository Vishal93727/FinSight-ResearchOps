"""Liveness and service identity checks."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_service_identity() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "finsight-researchops-api"


def test_health_returns_liveness_status() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "finsight-researchops-api"}
