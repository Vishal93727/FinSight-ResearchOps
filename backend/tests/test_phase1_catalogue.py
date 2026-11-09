"""Catalogue, provider and basic API contract tests."""


def test_health_and_request_id(client) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "phase1-test-001"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "phase1-test-001"


def test_provider_catalogue_requires_authentication(client) -> None:
    assert client.get("/api/v1/providers").status_code == 401


def test_root_identifies_researchops(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "finsight-researchops-api"
