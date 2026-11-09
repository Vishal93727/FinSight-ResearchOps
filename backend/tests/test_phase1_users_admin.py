"""Administrator-only account and role management tests."""

from app.core.security import hash_password
from app.models.entities import Role, User


def make_admin(db_session) -> User:
    admin_role = db_session.query(Role).filter_by(key="ADMIN").one()
    user = User(
        email="admin@example.org",
        full_name="Platform Administrator",
        password_hash=hash_password("A-strong-password-2026"),
        roles=[admin_role],
    )
    db_session.add(user)
    db_session.commit()
    return user


def login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_admin_can_list_users_and_replace_role(client, db_session) -> None:
    admin = make_admin(db_session)
    analyst_register = client.post(
        "/api/v1/auth/register",
        json={"email": "analyst2@example.com", "full_name": "Second Analyst", "password": "A-strong-password-2026"},
    )
    assert analyst_register.status_code == 201
    token = login(client, admin.email, "A-strong-password-2026")
    headers = {"Authorization": f"Bearer {token}"}
    listed = client.get("/api/v1/users", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    analyst_id = next(user["id"] for user in listed.json()["users"] if user["email"] == "analyst2@example.com")
    changed = client.patch(
        f"/api/v1/users/{analyst_id}/roles",
        headers=headers,
        json={"role_keys": ["RESEARCH_ANALYST", "QUANT_RESEARCHER"]},
    )
    assert changed.status_code == 200, changed.text
    assert {role["key"] for role in changed.json()["roles"]} == {"RESEARCH_ANALYST", "QUANT_RESEARCHER"}


def test_admin_cannot_remove_own_admin_role(client, db_session) -> None:
    admin = make_admin(db_session)
    token = login(client, admin.email, "A-strong-password-2026")
    response = client.patch(
        f"/api/v1/users/{admin.id}/roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"role_keys": ["RESEARCH_ANALYST"]},
    )
    assert response.status_code == 409
