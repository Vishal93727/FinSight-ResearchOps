"""Phase 5 acceptance: realised outcomes, drift, suggestions and operations APIs."""
from sqlalchemy import select
from app.models.entities import Role, User
from finsight.feedback.models import PredictionOutcome, DriftAssessment, StrategyPerformanceSnapshot


def _register(client, email: str) -> str:
    response = client.post("/api/v1/auth/register", json={
        "email": email, "full_name": email.split("@")[0].title(), "password": "Strong-password-2026!",
    })
    assert response.status_code == 201, response.text
    login = client.post("/api/v1/auth/login", data={"username": email, "password": "Strong-password-2026!"})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _add_role(db_session, email: str, role_key: str) -> None:
    user = db_session.scalar(select(User).where(User.email == email))
    role = db_session.scalar(select(Role).where(Role.key == role_key))
    assert user is not None and role is not None
    if role not in user.roles:
        user.roles.append(role)
    db_session.commit()


def _token_for_role(client, db_session, email: str, role: str) -> str:
    _register(client, email)
    _add_role(db_session, email, role)
    return client.post("/api/v1/auth/login", data={"username": email, "password": "Strong-password-2026!"}).json()["access_token"]


def test_feedback_routes_are_registered_and_no_live_broker_route_exists(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/feedback/outcomes": {"get", "post"},
        "/api/v1/feedback/summary": {"get"},
        "/api/v1/feedback/strategies/evaluate": {"post"},
        "/api/v1/feedback/strategies/evaluate-run": {"post"},
        "/api/v1/feedback/strategies": {"get"},
        "/api/v1/feedback/drift/check": {"post"},
        "/api/v1/feedback/drift-assessments": {"get"},
        "/api/v1/feedback/suggestions/generate": {"post"},
        "/api/v1/feedback/suggestions": {"get"},
        "/api/v1/feedback/suggestions/{suggestion_id}/decision": {"post"},
        "/api/v1/operations/summary": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths, path
        assert methods.issubset(paths[path]), (path, methods - paths[path].keys())
    assert not any("/live" in path for path in paths)


def test_prediction_outcomes_are_idempotent_and_aggregated(client, db_session):
    email = "phase5.outcomes@example.com"
    token = _token_for_role(client, db_session, email, "QUANT_RESEARCHER")
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "instrument_symbol": "MSFT", "forecast_date": "2026-10-01", "realised_date": "2026-10-08",
        "horizon_sessions": 5, "predicted_return": 0.025, "realised_return": 0.018,
        "benchmark_return": 0.012, "observation_source": "TEST_RECONCILIATION", "idempotency_key": "outcome-msft-001",
    }
    first = client.post("/api/v1/feedback/outcomes", headers=headers, json=body)
    second = client.post("/api/v1/feedback/outcomes", headers=headers, json=body)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    assert db_session.query(PredictionOutcome).count() == 1
    changed = body | {"realised_return": 0.04}
    conflict = client.post("/api/v1/feedback/outcomes", headers=headers, json=changed)
    assert conflict.status_code == 409
    summary = client.get("/api/v1/feedback/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["outcome_metrics"]["sample_count"] == 1


def test_strategy_performance_snapshot_is_persisted_with_benchmark_comparison(client, db_session):
    email = "phase5.strategy@example.com"
    token = _token_for_role(client, db_session, email, "PORTFOLIO_ANALYST")
    response = client.post("/api/v1/feedback/strategies/evaluate", headers={"Authorization": f"Bearer {token}"}, json={
        "strategy_key": "momentum-v1", "period_start": "2026-09-01T00:00:00Z", "period_end": "2026-10-01T00:00:00Z",
        "returns": [0.01, -0.005, 0.012, 0.004], "benchmark_returns": [0.004, -0.002, 0.006, 0.003],
    })
    assert response.status_code == 201, response.text
    assert response.json()["metrics"]["sample_count"] == 4
    assert response.json()["metrics"]["excess_return"] is not None
    assert db_session.query(StrategyPerformanceSnapshot).count() == 1


def test_drift_assessment_and_follow_up_suggestion_require_human_decision(client, db_session):
    email = "phase5.drift@example.com"
    token = _token_for_role(client, db_session, email, "QUANT_RESEARCHER")
    headers = {"Authorization": f"Bearer {token}"}
    baseline = [0.01, 0.02, 0.00, -0.01, 0.015, 0.006, -0.004, 0.008, 0.011, -0.003, 0.005, 0.009]
    current = [0.10, 0.12, 0.08, 0.13, 0.09, 0.11, 0.14, 0.07, 0.12, 0.10, 0.08, 0.13]
    checked = client.post("/api/v1/feedback/drift/check", headers=headers, json={
        "reference_features": {"daily_return": baseline}, "current_features": {"daily_return": current},
    })
    assert checked.status_code == 201, checked.text
    assert checked.json()["overall_status"] == "DRIFT"
    assert db_session.query(DriftAssessment).count() == 1
    generated = client.post("/api/v1/feedback/suggestions/generate", headers=headers)
    assert generated.status_code == 200, generated.text
    assert generated.json()
    suggestion_id = generated.json()[0]["id"]
    decision = client.post(f"/api/v1/feedback/suggestions/{suggestion_id}/decision", headers=headers,
        json={"status": "ACCEPTED", "comment": "Add a chronological investigation to the research backlog."})
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "ACCEPTED"


def test_feedback_role_boundaries_and_operations_summary(client, db_session):
    analyst_email = "phase5.analyst@example.com"
    analyst_token = _token_for_role(client, db_session, analyst_email, "RESEARCH_ANALYST")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    denied = client.post("/api/v1/feedback/outcomes", headers=analyst_headers, json={})
    assert denied.status_code == 403
    assert client.get("/api/v1/feedback/summary", headers=analyst_headers).status_code == 200
    unauthenticated = client.get("/api/v1/operations/summary")
    assert unauthenticated.status_code == 401

    admin_email = "phase5.ops.admin@example.com"
    admin_token = _token_for_role(client, db_session, admin_email, "ADMIN")
    summary = client.get("/api/v1/operations/summary", headers={"Authorization": f"Bearer {admin_token}"})
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert "jobs" in payload and "paper_execution" in payload and "governance" in payload
    assert payload["services"]["api"] == "ready"


def test_prometheus_metrics_endpoint_is_available(client):
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "finsight_http_requests_total" in response.text


def test_stale_job_recovery_is_dry_run_by_default_and_requires_admin_confirmation(client, db_session, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from app.models.entities import JobRecord
    admin_email = "phase5.recovery.admin@example.com"
    token = _token_for_role(client, db_session, admin_email, "ADMIN")
    old = datetime.now(UTC) - timedelta(hours=2)
    job = JobRecord(task_name="system.ping", status="QUEUE_FAILED", payload={}, created_at=old,
                    error_message="Temporary broker outage", created_by=db_session.scalar(select(User).where(User.email == admin_email)).id)
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    headers = {"Authorization": f"Bearer {token}"}
    preview = client.post("/api/v1/operations/recover-stale-jobs", headers=headers, json={"stale_after_minutes": 30})
    assert preview.status_code == 200, preview.text
    assert preview.json()["mode"] == "DRY_RUN"
    assert preview.json()["candidate_count"] == 1
    assert db_session.get(JobRecord, job.id).status == "QUEUE_FAILED"
    sent = []
    monkeypatch.setattr("app.services.jobs.enqueue_system_ping", lambda job_id: sent.append(job_id))
    confirmed = client.post("/api/v1/operations/recover-stale-jobs", headers=headers,
        json={"stale_after_minutes": 30, "confirm_requeue": True})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["results"][0]["status"] == "REQUEUED"
    assert sent == [job.id]
    assert db_session.get(JobRecord, job.id).status == "QUEUED"


def test_research_to_outcome_lineage_is_owned_and_snapshot_consistent(client, db_session):
    """A realised outcome keeps one user's succeeded run/model/paper lineage intact."""
    from decimal import Decimal
    from datetime import date
    from finsight.market_data.models import DataSnapshot
    from finsight.features.models import FeatureSetVersion
    from finsight.research.hypotheses.models import ResearchHypothesis
    from finsight.experiments.models import Experiment, ExperimentRun
    from finsight.governance.models import ModelVersion
    from finsight.execution.models import PaperAccount

    email = "phase5.lineage.owner@example.com"
    token = _token_for_role(client, db_session, email, "QUANT_RESEARCHER")
    owner = db_session.scalar(select(User).where(User.email == email))
    assert owner is not None

    snapshot = DataSnapshot(
        provider_key="manual_upload", instrument_symbol="MSFT", interval="1d",
        start_date=date(2026, 1, 1), end_date=date(2026, 10, 30), status="READY",
        file_path="/test/msft.parquet", storage_format="parquet", sha256="a" * 64,
        row_count=200, manifest={"source": "test"}, created_by=owner.id,
    )
    db_session.add(snapshot)
    db_session.flush()
    feature_set = FeatureSetVersion(
        feature_key="msft-core", version=1, description="Test feature lineage",
        definition={"columns": ["close", "returns_1d"]}, source_snapshot_id=snapshot.id,
        definition_sha256="b" * 64, created_by=owner.id,
    )
    hypothesis = ResearchHypothesis(
        title="MSFT test hypothesis", symbol="MSFT", thesis="Test a bounded momentum effect",
        rationale="Acceptance test", status="APPROVED", evidence=[], decision_note="Approved for test",
        version=1, owner_user_id=owner.id,
    )
    db_session.add_all([feature_set, hypothesis])
    db_session.flush()
    experiment = Experiment(
        name="MSFT walk-forward test", hypothesis_id=hypothesis.id, instrument_symbol="MSFT",
        dataset_snapshot_id=snapshot.id, feature_set_version_id=feature_set.id,
        configuration={"evaluation": "walk_forward"}, configuration_sha256="c" * 64,
        status="COMPLETED", created_by=owner.id,
    )
    db_session.add(experiment)
    db_session.flush()
    run = ExperimentRun(
        experiment_id=experiment.id, run_number=1, status="SUCCEEDED", random_seed=42,
        metrics={"rmse": 0.012}, artifacts={"equity_curve": "test://equity"},
    )
    model = ModelVersion(
        model_key="msft-momentum", version="1.0.0", model_family="XGBOOST",
        dataset_snapshot_id=snapshot.id, feature_set_version_id=feature_set.id,
        metrics={"rmse": 0.012}, configuration={"seed": 42},
        risk_decision="PASS", state="ACTIVE", created_by=owner.id,
    )
    account = PaperAccount(
        name="Lineage acceptance account", currency="USD", initial_cash=Decimal("100000"),
        cash_balance=Decimal("100000"), created_by=owner.id,
    )
    db_session.add_all([run, model, account])
    db_session.commit()

    body = {
        "instrument_symbol": "MSFT", "forecast_date": "2026-10-01", "realised_date": "2026-10-30",
        "horizon_sessions": 21, "predicted_return": 0.025, "realised_return": 0.018,
        "model_version_id": model.id, "experiment_run_id": run.id,
        "paper_account_id": account.id, "idempotency_key": "msft-lineage-check-001",
    }
    response = client.post("/api/v1/feedback/outcomes", headers={"Authorization": f"Bearer {token}"}, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["model_version_id"] == model.id
    assert response.json()["experiment_run_id"] == run.id
    assert response.json()["paper_account_id"] == account.id

    # Populate enough realised observations to activate the calibration-bias suggestion rule.
    for offset in range(1, 10):
        forecast_day = offset + 1
        extra = client.post("/api/v1/feedback/outcomes",
            headers={"Authorization": f"Bearer {token}"}, json={
                "instrument_symbol": "MSFT", "forecast_date": f"2026-10-{forecast_day:02d}",
                "realised_date": "2026-10-30", "horizon_sessions": 10,
                "predicted_return": 0.05, "realised_return": 0.01,
                "idempotency_key": f"msft-bias-sample-{offset:02d}",
            })
        assert extra.status_code == 201, extra.text

    # A different user cannot attach another user's model/run/account to their outcome ledger.
    other_email = "phase5.lineage.other@example.com"
    other_token = _token_for_role(client, db_session, other_email, "QUANT_RESEARCHER")
    denied = client.post("/api/v1/feedback/outcomes",
        headers={"Authorization": f"Bearer {other_token}"},
        json=body | {"idempotency_key": "msft-lineage-other-001"})
    assert denied.status_code == 404
    denied_account = client.post("/api/v1/feedback/outcomes",
        headers={"Authorization": f"Bearer {other_token}"},
        json={
            "instrument_symbol": "MSFT", "forecast_date": "2026-10-01", "realised_date": "2026-10-30",
            "horizon_sessions": 21, "predicted_return": 0.025, "realised_return": 0.018,
            "paper_account_id": account.id, "idempotency_key": "msft-account-other-001",
        })
    assert denied_account.status_code == 404

    mismatched_features = FeatureSetVersion(
        feature_key="msft-alternate", version=1, description="Wrong feature lineage",
        definition={"columns": ["close"]}, source_snapshot_id=snapshot.id,
        definition_sha256="d" * 64, created_by=owner.id,
    )
    db_session.add(mismatched_features)
    db_session.flush()
    mismatched_model = ModelVersion(
        model_key="msft-momentum-wrong-lineage", version="1.0.0", model_family="XGBOOST",
        dataset_snapshot_id=snapshot.id, feature_set_version_id=mismatched_features.id,
        metrics={"rmse": 0.012}, configuration={"seed": 42}, risk_decision="PASS",
        state="ACTIVE", created_by=owner.id,
    )
    db_session.add(mismatched_model)
    db_session.commit()
    conflict = client.post("/api/v1/feedback/outcomes",
        headers={"Authorization": f"Bearer {token}"},
        json=body | {"model_version_id": mismatched_model.id,
                     "idempotency_key": "msft-lineage-mismatch-001"})
    assert conflict.status_code == 409

    # Continue the same lineage through strategy monitoring, drift, suggestions and a human decision.
    strategy = client.post("/api/v1/feedback/strategies/evaluate",
        headers={"Authorization": f"Bearer {token}"}, json={
            "strategy_key": "MSFT:walk-forward-v1",
            "period_start": "2026-10-01T00:00:00Z", "period_end": "2026-10-04T00:00:00Z",
            "returns": [-0.05, -0.03, -0.04], "benchmark_returns": [0.005, 0.004, 0.006],
            "source_reference": f"experiment_run:{run.id}",
        })
    assert strategy.status_code == 201, strategy.text
    assert strategy.json()["metrics"]["sample_count"] == 3
    assert strategy.json()["metrics"]["annualized_sharpe"] < 0

    current_snapshot = DataSnapshot(
        provider_key="manual_upload", instrument_symbol="MSFT", interval="1d",
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 30), status="READY",
        file_path="/test/msft-current.parquet", storage_format="parquet", sha256="e" * 64,
        row_count=22, manifest={"role": "current-drift-window"}, created_by=owner.id,
    )
    db_session.add(current_snapshot)
    db_session.commit()
    baseline = [0.01, 0.02, 0.00, -0.01, 0.015, 0.006, -0.004, 0.008, 0.011, -0.003, 0.005, 0.009]
    shifted = [0.10, 0.12, 0.08, 0.13, 0.09, 0.11, 0.14, 0.07, 0.12, 0.10, 0.08, 0.13]
    drift = client.post("/api/v1/feedback/drift/check",
        headers={"Authorization": f"Bearer {token}"}, json={
            "model_version_id": model.id, "reference_snapshot_id": snapshot.id,
            "current_snapshot_id": current_snapshot.id,
            "reference_features": {"daily_return": baseline},
            "current_features": {"daily_return": shifted},
        })
    assert drift.status_code == 201, drift.text
    assert drift.json()["overall_status"] == "DRIFT"

    generated = client.post("/api/v1/feedback/suggestions/generate",
        headers={"Authorization": f"Bearer {token}"})
    assert generated.status_code == 200, generated.text
    titles = {item["title"] for item in generated.json()}
    assert "Investigate feature-distribution drift" in titles
    assert "Review strategy performance degradation" in titles
    assert "Review forecast bias calibration" in titles
    proposal = generated.json()[0]
    decision = client.post(f"/api/v1/feedback/suggestions/{proposal['id']}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "ACCEPTED", "comment": "Investigate the linked snapshot and schedule a new holdout experiment."})
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "ACCEPTED"

    summary = client.get("/api/v1/feedback/summary", headers={"Authorization": f"Bearer {token}"})
    assert summary.status_code == 200, summary.text
    dashboard = summary.json()
    assert dashboard["outcome_count"] == 10
    assert dashboard["strategy_snapshots"][0]["metrics"]["sample_count"] == 3
    assert dashboard["drift"]["total"] == 1
    assert dashboard["proposed_suggestions"] == len(generated.json()) - 1



def test_drift_check_cannot_reference_another_users_model_or_snapshot(client, db_session):
    """Monitoring links must not become an IDOR path into another researcher's lineage."""
    from datetime import date
    from finsight.market_data.models import DataSnapshot
    from finsight.features.models import FeatureSetVersion
    from finsight.governance.models import ModelVersion

    owner_email = "phase5.drift.owner@example.com"
    owner_token = _token_for_role(client, db_session, owner_email, "QUANT_RESEARCHER")
    owner = db_session.scalar(select(User).where(User.email == owner_email))
    snapshot = DataSnapshot(
        provider_key="manual_upload", instrument_symbol="MSFT", interval="1d",
        start_date=date(2026, 1, 1), end_date=date(2026, 10, 30), status="READY",
        file_path="/test/phase5-msft.parquet", storage_format="parquet", sha256="e" * 64,
        row_count=200, manifest={}, created_by=owner.id,
    )
    db_session.add(snapshot)
    db_session.flush()
    features = FeatureSetVersion(
        feature_key="phase5-drift-features", version=1, description="Drift reference features",
        definition={"columns": ["close"]}, source_snapshot_id=snapshot.id,
        definition_sha256="f" * 64, created_by=owner.id,
    )
    db_session.add(features)
    db_session.flush()
    model = ModelVersion(
        model_key="phase5-drift-model", version="1.0.0", model_family="RIDGE",
        dataset_snapshot_id=snapshot.id, feature_set_version_id=features.id,
        metrics={"rmse": 0.01}, configuration={}, risk_decision="PASS",
        state="ACTIVE", created_by=owner.id,
    )
    db_session.add(model)
    db_session.commit()

    other_email = "phase5.drift.other@example.com"
    other_token = _token_for_role(client, db_session, other_email, "QUANT_RESEARCHER")
    sample = [float(value) for value in range(10)]
    denied_snapshot = client.post("/api/v1/feedback/drift/check",
        headers={"Authorization": f"Bearer {other_token}"}, json={
            "reference_snapshot_id": snapshot.id,
            "reference_features": {"close": sample}, "current_features": {"close": sample},
        })
    assert denied_snapshot.status_code == 404
    denied_model = client.post("/api/v1/feedback/drift/check",
        headers={"Authorization": f"Bearer {other_token}"}, json={
            "model_version_id": model.id,
            "reference_features": {"close": sample}, "current_features": {"close": sample},
        })
    assert denied_model.status_code == 404

    # The owner can assess its training snapshot; the model's reference lineage is explicit.
    accepted = client.post("/api/v1/feedback/drift/check",
        headers={"Authorization": f"Bearer {owner_token}"}, json={
            "model_version_id": model.id, "reference_snapshot_id": snapshot.id,
            "reference_features": {"close": sample}, "current_features": {"close": sample},
        })
    assert accepted.status_code == 201, accepted.text


def test_operations_summary_reports_worker_and_recent_failure_metadata(client, db_session):
    from datetime import UTC, datetime
    from app.models.entities import JobRecord
    email = "phase5.ops.extended@example.com"
    token = _token_for_role(client, db_session, email, "ADMIN")
    user = db_session.scalar(select(User).where(User.email == email))
    db_session.add(JobRecord(task_name="ml.evaluate", status="FAILED", payload={},
        error_message="Model dependency unavailable", completed_at=datetime.now(UTC), created_by=user.id))
    db_session.commit()
    response = client.get("/api/v1/operations/summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["services"]["worker"] in {"ready", "unavailable"}
    assert isinstance(payload["worker_names"], list)
    assert isinstance(payload["stale_job_count"], int)
    assert payload["recent_failures"][0]["task_name"] == "ml.evaluate"
    assert payload["recent_failures"][0]["failure_recorded"] is True
    assert "error_message" not in payload["recent_failures"][0]


def test_completed_backtest_run_can_feed_strategy_monitoring_with_hash_verification(
    client, db_session, tmp_path, monkeypatch,
):
    """End-to-end API bridge from a successful Phase 2 run into Phase 5 monitoring."""
    import hashlib
    import pandas as pd
    from datetime import date
    from finsight.market_data.models import DataSnapshot
    from finsight.features.models import FeatureSetVersion
    from finsight.research.hypotheses.models import ResearchHypothesis
    from finsight.experiments.models import Experiment, ExperimentRun

    email = "phase5.run-import@example.com"
    token = _token_for_role(client, db_session, email, "QUANT_RESEARCHER")
    owner = db_session.scalar(select(User).where(User.email == email))
    snapshot = DataSnapshot(
        provider_key="manual_upload", instrument_symbol="MSFT", interval="1d",
        start_date=date(2026, 1, 1), end_date=date(2026, 10, 30), status="READY",
        file_path="/not-read/by-this-test.parquet", storage_format="parquet", sha256="a" * 64,
        row_count=200, manifest={}, created_by=owner.id,
    )
    db_session.add(snapshot)
    db_session.flush()
    features = FeatureSetVersion(
        feature_key="monitor-features", version=1, description="Monitoring feature lineage",
        definition={"columns": ["close"]}, source_snapshot_id=snapshot.id,
        definition_sha256="b" * 64, created_by=owner.id,
    )
    hypothesis = ResearchHypothesis(
        title="Monitoring workflow hypothesis", symbol="MSFT", thesis="Test return monitoring",
        rationale="End-to-end acceptance", status="APPROVED", evidence=[],
        decision_note="Test approved", version=1, owner_user_id=owner.id,
    )
    db_session.add_all([features, hypothesis])
    db_session.flush()
    experiment = Experiment(
        name="Monitor end-to-end", hypothesis_id=hypothesis.id, instrument_symbol="MSFT",
        dataset_snapshot_id=snapshot.id, feature_set_version_id=features.id,
        configuration={"baseline": "moving_average_crossover"}, configuration_sha256="c" * 64,
        status="COMPLETED", created_by=owner.id,
    )
    db_session.add(experiment)
    db_session.flush()
    artifact = tmp_path / "equity_curve.parquet"
    artifact.write_bytes(b"test parquet bytes; pandas reader is stubbed")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    run = ExperimentRun(
        experiment_id=experiment.id, run_number=1, status="SUCCEEDED", random_seed=42,
        metrics={"total_return": 0.04},
        artifacts={"equity_curve_path": str(artifact), "equity_curve_sha256": digest},
    )
    db_session.add(run)
    db_session.commit()

    from types import SimpleNamespace
    monkeypatch.setattr("app.api.v1.feedback.get_settings", lambda: SimpleNamespace(data_storage_path=str(tmp_path)))
    monkeypatch.setattr(pd, "read_parquet", lambda _: pd.DataFrame({
        "date": pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-05"], utc=True),
        "strategy_return": [0.01, -0.004, 0.008],
    }))
    response = client.post("/api/v1/feedback/strategies/evaluate-run",
        headers={"Authorization": f"Bearer {token}"}, json={"experiment_run_id": run.id})
    assert response.status_code == 201, response.text
    assert response.json()["strategy_key"] == "MSFT:moving_average_crossover"
    assert response.json()["metrics"]["sample_count"] == 3
    assert f"experiment_run:{run.id}" in response.json()["source_reference"]
    replay = client.post("/api/v1/feedback/strategies/evaluate-run",
        headers={"Authorization": f"Bearer {token}"}, json={"experiment_run_id": run.id})
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == response.json()["id"]
    assert db_session.query(StrategyPerformanceSnapshot).count() == 1

    artifact.write_bytes(b"tampered artifact")
    tampered = client.post("/api/v1/feedback/strategies/evaluate-run",
        headers={"Authorization": f"Bearer {token}"}, json={"experiment_run_id": run.id})
    assert tampered.status_code == 409

    other = _token_for_role(client, db_session, "phase5.run-import.other@example.com", "QUANT_RESEARCHER")
    foreign = client.post("/api/v1/feedback/strategies/evaluate-run",
        headers={"Authorization": f"Bearer {other}"}, json={"experiment_run_id": run.id})
    assert foreign.status_code == 404


def test_container_and_frontend_health_proxies_use_versioned_api_paths():
    """The Compose health probe and both web-server aliases must reach FastAPI's /api/v1 health routes."""
    from pathlib import Path
    import yaml

    root = Path(__file__).resolve().parents[2]
    for compose_name in ("compose.yaml", "docker-compose.yml"):
        compose = yaml.safe_load((root / compose_name).read_text(encoding="utf-8"))
        health_test = compose["services"]["api"]["healthcheck"]["test"]
        assert any("/api/v1/health/ready" in str(part) for part in health_test)

    nginx = (root / "apps/web/nginx.conf").read_text(encoding="utf-8")
    assert "proxy_pass http://api:8000/api/v1/health;" in nginx
    vite = (root / "apps/web/vite.config.ts").read_text(encoding="utf-8")
    assert "rewrite: () => '/api/v1/health'" in vite
