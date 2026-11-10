"""Phase-one identity and RBAC acceptance tests."""

from app.core.security import hash_password, verify_password


def test_password_hash_is_salted_and_verifies() -> None:
    first = hash_password("A-strong-password-2026")
    second = hash_password("A-strong-password-2026")
    assert first != second
    assert verify_password("A-strong-password-2026", first)
    assert not verify_password("wrong-password", first)


def test_register_login_and_protected_me(client) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "Analyst@example.com", "full_name": "Test Analyst", "password": "A-strong-password-2026"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["email"] == "analyst@example.com"
    assert response.json()["roles"][0]["key"] == "RESEARCH_ANALYST"

    login = client.post(
        "/api/v1/auth/login",
        data={"username": "analyst@example.com", "password": "A-strong-password-2026"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == "Test Analyst"


def test_duplicate_registration_is_rejected(client) -> None:
    payload = {"email": "same@example.com", "full_name": "Same User", "password": "A-strong-password-2026"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_analyst_cannot_create_instrument(client) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "analyst@example.com", "full_name": "Analyst", "password": "A-strong-password-2026"},
    )
    assert registration.status_code == 201
    token = client.post(
        "/api/v1/auth/login", data={"username": "analyst@example.com", "password": "A-strong-password-2026"}
    ).json()["access_token"]
    response = client.post(
        "/api/v1/instruments",
        json={"symbol": "MSFT", "name": "Microsoft Corporation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_instrument_requires_authentication(client) -> None:
    assert client.get("/api/v1/instruments").status_code == 401
