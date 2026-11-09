"""Phase 2 acceptance tests for hypothesis approval and reproducible specifications."""
from datetime import date

from sqlalchemy import select

from app.models.entities import DataSnapshot, Role, User


def _register_quant_user(client) -> tuple[str, str]:
    email = "quant.phase2@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Quant Researcher", "password": "A-strong-password-2026"},
    )
    return email, client.post(
        "/api/v1/auth/login", data={"username": email, "password": "A-strong-password-2026"}
    ).json()["access_token"]


def _add_role(db_session, email: str, role_key: str) -> None:
    user = db_session.scalar(select(User).where(User.email == email))
    role = db_session.scalar(select(Role).where(Role.key == role_key))
    assert user is not None and role is not None
    user.roles.append(role)
    db_session.commit()


def test_hypothesis_requires_review_and_records_evidence(client, db_session) -> None:
    email, analyst_token = _register_quant_user(client)
    headers = {"Authorization": f"Bearer {analyst_token}"}
    payload = {
        "title": "Momentum persistence in liquid technology shares",
        "symbol": "MSFT",
        "thesis": "Recent positive returns may persist over a short horizon in liquid large-cap equities.",
        "rationale": "This hypothesis will be evaluated with chronological train, validation and test windows.",
        "evidence": [
            {
                "source_type": "SEC_FILING",
                "title": "Annual filing reference",
                "source_uri": "https://www.sec.gov/edgar/search/",
                "excerpt": "Example evidence excerpt",
            }
        ],
    }
    created = client.post("/api/v1/research/hypotheses", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    hypothesis = created.json()
    assert hypothesis["status"] == "DRAFT"
    assert hypothesis["symbol"] == "MSFT"
    assert len(hypothesis["evidence"]) == 1
    import hashlib
    assert hypothesis["evidence"][0]["excerpt_sha256"] == hashlib.sha256(b"Example evidence excerpt").hexdigest()

    submitted = client.post(
        f"/api/v1/research/hypotheses/{hypothesis['id']}/submit-review", headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "UNDER_REVIEW"

    # A research analyst cannot self-approve a hypothesis.
    denied = client.post(
        f"/api/v1/research/hypotheses/{hypothesis['id']}/decision",
        json={"decision": "APPROVE", "note": "Reviewed"},
        headers=headers,
    )
    assert denied.status_code == 403

    _add_role(db_session, email, "RISK_REVIEWER")
    reviewer_token = client.post(
        "/api/v1/auth/login", data={"username": email, "password": "A-strong-password-2026"}
    ).json()["access_token"]
    approved = client.post(
        f"/api/v1/research/hypotheses/{hypothesis['id']}/decision",
        json={"decision": "APPROVE", "note": "Evidence is sufficient for a controlled experiment."},
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["version"] == 3


def test_feature_set_and_experiment_keep_versioned_provenance(client, db_session) -> None:
    email, _ = _register_quant_user(client)
    _add_role(db_session, email, "RISK_REVIEWER")
    _add_role(db_session, email, "QUANT_RESEARCHER")
    headers = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', data={'username': email, 'password': 'A-strong-password-2026'}).json()['access_token']}"}
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    snapshot = DataSnapshot(
        provider_key="manual_upload",
        instrument_symbol="MSFT",
        interval="1d",
        start_date=date(2021, 1, 1),
        end_date=date(2025, 12, 31),
        status="READY",
        file_path="/tmp/msft-fixture.parquet",
        storage_format="parquet",
        sha256="a" * 64,
        row_count=1250,
        manifest={"timezone": "UTC", "adjustment_policy": "provider_defined"},
        created_by=user.id,
    )
    benchmark_snapshot = DataSnapshot(
        provider_key="manual_upload", instrument_symbol="SPY", interval="1d",
        start_date=date(2021, 1, 1), end_date=date(2025, 12, 31), status="READY",
        file_path="/tmp/spy-fixture.parquet", storage_format="parquet", sha256="d" * 64,
        row_count=1250, manifest={"timezone": "UTC"}, created_by=user.id,
    )
    db_session.add_all([snapshot, benchmark_snapshot])
    db_session.commit()

    hypothesis_response = client.post(
        "/api/v1/research/hypotheses",
        json={
            "title": "MSFT short-horizon trend hypothesis",
            "symbol": "MSFT",
            "thesis": "A positive five-session momentum signal may predict next-session returns.",
        },
        headers=headers,
    )
    assert hypothesis_response.status_code == 201, hypothesis_response.text
    hypothesis_id = hypothesis_response.json()["id"]
    submit = client.post(f"/api/v1/research/hypotheses/{hypothesis_id}/submit-review", headers=headers)
    assert submit.status_code == 200, submit.text
    decision = client.post(
        f"/api/v1/research/hypotheses/{hypothesis_id}/decision",
        json={"decision": "APPROVE", "note": "Approved for an offline experiment."},
        headers=headers,
    )
    assert decision.status_code == 200, decision.text

    feature_response = client.post(
        "/api/v1/features/versions",
        json={
            "feature_key": "ohlcv_momentum",
            "description": "Close-derived momentum and volatility features.",
            "definition": {"features": ["return_1d", "momentum_5d", "volatility_20d"], "target": "next_day_return"},
            "source_snapshot_id": snapshot.id,
        },
        headers=headers,
    )
    assert feature_response.status_code == 201, feature_response.text
    feature = feature_response.json()
    assert feature["version"] == 1
    assert len(feature["definition_sha256"]) == 64

    experiment_payload = {
        "name": "MSFT momentum baseline 2025 holdout",
        "hypothesis_id": hypothesis_id,
        "dataset_snapshot_id": snapshot.id,
        "feature_set_version_id": feature["id"],
        "benchmark_snapshot_id": benchmark_snapshot.id,
        "configuration": {
            "model_family": "baseline",
            "baseline": "buy_and_hold",
            "target": "next_day_return",
            "prediction_horizon_days": 1,
            "train_start": "2021-01-01",
            "train_end": "2023-12-31",
            "validation_start": "2024-01-02",
            "validation_end": "2024-06-30",
            "test_start": "2024-07-02",
            "test_end": "2025-12-31",
            "random_seed": 42,
            "commission_bps": 5,
            "slippage_bps": 5,
            "benchmark_symbol": "SPY",
        },
    }
    experiment = client.post("/api/v1/experiments", json=experiment_payload, headers=headers)
    assert experiment.status_code == 201, experiment.text
    assert experiment.json()["status"] == "DRAFT"
    assert len(experiment.json()["configuration_sha256"]) == 64
    assert experiment.json()["dataset_snapshot_id"] == snapshot.id
    assert experiment.json()["benchmark_snapshot_id"] == benchmark_snapshot.id


def test_experiment_config_rejects_overlapping_temporal_windows() -> None:
    from pydantic import ValidationError
    import pytest

    from finsight.experiments.config import ExperimentConfiguration

    with pytest.raises(ValidationError):
        ExperimentConfiguration(
            train_start="2021-01-01", train_end="2023-12-31",
            validation_start="2023-06-01", validation_end="2024-06-30",
            test_start="2024-07-01", test_end="2025-12-31",
        )


def test_experiment_run_submission_is_idempotent(client, db_session, monkeypatch) -> None:
    from datetime import date

    from finsight.experiments.models import Experiment, ExperimentRun
    from finsight.experiments.registry import configuration_sha256
    from finsight.features.models import FeatureSetVersion
    from finsight.market_data.models import DataSnapshot
    from finsight.research.hypotheses.models import ResearchHypothesis

    email, _ = _register_quant_user(client)
    _add_role(db_session, email, "QUANT_RESEARCHER")
    token = client.post(
        "/api/v1/auth/login", data={"username": email, "password": "A-strong-password-2026"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "quant-run-001"}
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None

    snapshot = DataSnapshot(
        provider_key="manual_upload", instrument_symbol="MSFT", interval="1d",
        start_date=date(2021, 1, 1), end_date=date(2025, 12, 31), status="READY",
        file_path="/tmp/msft-fixture.parquet", storage_format="parquet", sha256="b" * 64,
        row_count=1250, manifest={"timezone": "UTC"}, created_by=user.id,
    )
    db_session.add(snapshot)
    db_session.flush()
    hypothesis = ResearchHypothesis(
        title="MSFT momentum hypothesis", symbol="MSFT",
        thesis="Positive short-term momentum may persist over the next trading session.",
        rationale="Controlled offline experiment", status="APPROVED", evidence=[],
        decision_note="Approved for test", version=3, owner_user_id=user.id,
    )
    db_session.add(hypothesis)
    db_session.flush()
    feature_set = FeatureSetVersion(
        feature_key="ohlcv_momentum", version=1, description="Baseline test features",
        definition={"features": ["return_1d"], "target": "next_day_return"},
        source_snapshot_id=snapshot.id, definition_sha256="c" * 64, created_by=user.id,
    )
    db_session.add(feature_set)
    db_session.flush()
    configuration = {
        "model_family": "baseline", "baseline": "buy_and_hold", "target": "next_day_return",
        "prediction_horizon_days": 1, "purge_gap_days": 1,
        "train_start": "2021-01-01", "train_end": "2023-12-31",
        "validation_start": "2024-01-02", "validation_end": "2024-06-30",
        "test_start": "2024-07-02", "test_end": "2025-12-31",
        "random_seed": 17, "commission_bps": 5, "slippage_bps": 5, "benchmark_symbol": "SPY",
    }
    experiment = Experiment(
        name="MSFT baseline idempotency test", hypothesis_id=hypothesis.id,
        instrument_symbol="MSFT", dataset_snapshot_id=snapshot.id,
        feature_set_version_id=feature_set.id, configuration=configuration,
        configuration_sha256=configuration_sha256(configuration), status="DRAFT", created_by=user.id,
    )
    db_session.add(experiment)
    db_session.commit()

    queued: list[str] = []
    monkeypatch.setattr("app.api.v1.research.enqueue_experiment_run", queued.append)

    first = client.post(f"/api/v1/experiments/{experiment.id}/runs", json={}, headers=headers)
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "QUEUED"
    assert first.json()["random_seed"] == 17

    repeated = client.post(f"/api/v1/experiments/{experiment.id}/runs", json={}, headers=headers)
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["id"] == first.json()["id"]
    assert queued == [first.json()["id"]]

    listed = client.get(f"/api/v1/experiments/{experiment.id}/runs", headers=headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1

    # A queue outage is visible, and retrying the same key reuses the failed run record.
    def fail_enqueue(_: str) -> None:
        raise RuntimeError("simulated Redis outage")

    failed_headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "quant-run-retry-002"}
    monkeypatch.setattr("app.api.v1.research.enqueue_experiment_run", fail_enqueue)
    failed = client.post(f"/api/v1/experiments/{experiment.id}/runs", json={}, headers=failed_headers)
    assert failed.status_code == 503
    monkeypatch.setattr("app.api.v1.research.enqueue_experiment_run", queued.append)
    retried = client.post(f"/api/v1/experiments/{experiment.id}/runs", json={}, headers=failed_headers)
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "QUEUED"
    assert queued == [first.json()["id"], retried.json()["id"]]
    final_list = client.get(f"/api/v1/experiments/{experiment.id}/runs", headers=headers)
    assert len(final_list.json()) == 2

    from finsight.risk.models import ExperimentRiskReview
    first_run = db_session.get(ExperimentRun, first.json()["id"])
    assert first_run is not None
    first_run.status = "SUCCEEDED"
    first_run.metrics = {"total_return": 0.12, "annualized_return": 0.08, "sharpe_ratio": 1.1,
                         "max_drawdown": -0.07, "annualized_volatility": 0.15,
                         "benchmark_total_return": 0.05, "information_ratio": 0.6}
    db_session.add(ExperimentRiskReview(
        run_id=first_run.id, decision="PASS", policy_version="phase2-v1",
        limits={"max_drawdown_abs": 0.2}, observed_metrics={"max_drawdown": -0.07},
        breaches=[], warnings=[], deterministic=True, override_allowed=False,
    ))
    db_session.commit()
    risk_response = client.get(
        f"/api/v1/experiments/{experiment.id}/runs/{first_run.id}/risk-review", headers=headers
    )
    assert risk_response.status_code == 200, risk_response.text
    assert risk_response.json()["decision"] == "PASS"
    assert risk_response.json()["override_allowed"] is False
    comparison_response = client.get(
        f"/api/v1/experiments/{experiment.id}/runs/comparison", headers=headers
    )
    assert comparison_response.status_code == 200, comparison_response.text
    assert comparison_response.json()[0]["risk_decision"] == "PASS"
    assert comparison_response.json()[0]["benchmark_total_return"] == 0.05
