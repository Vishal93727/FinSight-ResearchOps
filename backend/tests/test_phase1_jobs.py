"""Background job record and idempotency acceptance tests."""


def test_job_enqueue_and_idempotency(client, monkeypatch) -> None:
    from app.api.v1 import jobs as jobs_api

    monkeypatch.setattr(jobs_api, "enqueue_system_ping", lambda job_id: None)
    client.post(
        "/api/v1/auth/register",
        json={"email": "job.user@example.com", "full_name": "Job User", "password": "A-strong-password-2026"},
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "job.user@example.com", "password": "A-strong-password-2026"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"idempotency_key": "job-ping-once-0001"}
    first = client.post("/api/v1/jobs/ping", headers=headers, json=payload)
    second = client.post("/api/v1/jobs/ping", headers=headers, json=payload)
    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/api/v1/jobs/{first.json()['id']}", headers=headers).status_code == 200


def test_job_queue_failure_is_visible(client, monkeypatch) -> None:
    from app.api.v1 import jobs as jobs_api

    def fail_enqueue(job_id: str) -> None:
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(jobs_api, "enqueue_system_ping", fail_enqueue)
    client.post(
        "/api/v1/auth/register",
        json={"email": "job.fail@example.com", "full_name": "Job Failure", "password": "A-strong-password-2026"},
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "job.fail@example.com", "password": "A-strong-password-2026"},
    ).json()["access_token"]
    response = client.post(
        "/api/v1/jobs/ping", headers={"Authorization": f"Bearer {token}"}, json={}
    )
    assert response.status_code == 503
    assert "queue is unavailable" in response.json()["detail"].lower()
