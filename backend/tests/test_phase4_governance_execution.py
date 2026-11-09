"""Phase 4 acceptance: governance gates, deterministic paper broker and RL safety contracts."""
from decimal import Decimal
from sqlalchemy import select

from app.models.entities import Role, User
from finsight.execution.models import PaperAccount, PaperFill, PaperLedgerEntry, PaperOrder, PaperPosition
from finsight.governance.models import ModelVersion, ModelRiskReview, ModelGovernanceDecision
from finsight.market_data.models import Instrument
from finsight.risk.governance import evaluate_model_candidate, evaluate_paper_order


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


def test_model_risk_policy_requires_oos_and_verified_artifact() -> None:
    good = {"test_rows": 80, "directional_accuracy": 0.53, "rmse": 0.025,
            "artifact_integrity": "VERIFIED"}
    assert evaluate_model_candidate(good, out_of_sample=True)["decision"] == "PASS"
    no_oos = evaluate_model_candidate(good, out_of_sample=False)
    assert no_oos["decision"] == "REJECT"
    assert no_oos["deterministic"] is True and no_oos["override_allowed"] is False
    no_artifact = evaluate_model_candidate(good | {"artifact_integrity": "MISSING"}, out_of_sample=True)
    assert no_artifact["decision"] == "REJECT"
    low_observations = evaluate_model_candidate(good | {"test_rows": 3}, out_of_sample=True)
    assert low_observations["decision"] == "REVIEW"


def test_paper_order_risk_engine_is_independent_and_checks_post_trade_exposure() -> None:
    base = dict(side="BUY", quantity=Decimal("10"), reference_price=Decimal("100"),
        cash_balance=Decimal("10000"), current_equity=Decimal("10000"),
        current_gross_exposure=Decimal("0"), symbol_position=Decimal("0"),
        account_limits={"fee_bps": 5, "max_order_notional": "2500", "max_gross_exposure": 1.0, "max_symbol_exposure": 0.4},
        kill_switch=False)
    assert evaluate_paper_order(**base)["decision"] == "PASS"
    assert evaluate_paper_order(**(base | {"kill_switch": True}))["decision"] == "REJECT"
    assert evaluate_paper_order(**(base | {"quantity": Decimal("30")}))["decision"] == "REJECT"
    assert evaluate_paper_order(**(base | {"side": "SELL", "symbol_position": Decimal("2")}))["decision"] == "REJECT"


def _seed_promoted_model(db_session, creator: User, key: str = "ridge-msft", version: str = "1.0.0") -> ModelVersion:
    item = ModelVersion(model_key=key, version=version, model_family="ridge", metrics={
        "test_rows": 100, "directional_accuracy": 0.55, "rmse": 0.02,
        "artifact_integrity": "VERIFIED"}, configuration={"split_method": "chronological_no_shuffle"},
        risk_decision="PASS", state="CANDIDATE", created_by=creator.id)
    db_session.add(item); db_session.flush()
    db_session.add(ModelRiskReview(model_version_id=item.id, decision="PASS", policy_version="model-governance-v1",
        limits={}, observed_metrics=item.metrics, breaches=[], warnings=[], deterministic=True))
    db_session.commit()
    return item


def test_model_promotion_requires_independent_approval_and_rollback_is_audited(client, db_session) -> None:
    creator_email = "phase4.model.creator@example.com"
    reviewer_email = "phase4.model.reviewer@example.com"
    admin_email = "phase4.model.admin@example.com"
    creator_token = _register(client, creator_email)
    _add_role(db_session, creator_email, "QUANT_RESEARCHER")
    reviewer_token = _register(client, reviewer_email)
    _add_role(db_session, reviewer_email, "RISK_REVIEWER")
    reviewer_token = client.post("/api/v1/auth/login", data={"username": reviewer_email, "password": "Strong-password-2026!"}).json()["access_token"]
    admin_token = _register(client, admin_email)
    _add_role(db_session, admin_email, "ADMIN")
    admin_token = client.post("/api/v1/auth/login", data={"username": admin_email, "password": "Strong-password-2026!"}).json()["access_token"]
    creator = db_session.scalar(select(User).where(User.email == creator_email))
    assert creator is not None

    v1 = _seed_promoted_model(db_session, creator, version="1.0.0")
    creator_headers = {"Authorization": f"Bearer {creator_token}"}
    self_approve = client.post(f"/api/v1/governance/models/{v1.id}/decision", headers=creator_headers,
        json={"decision": "APPROVE", "comment": "Self approval should fail"})
    assert self_approve.status_code == 403
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
    approved = client.post(f"/api/v1/governance/models/{v1.id}/decision", headers=reviewer_headers,
        json={"decision": "APPROVE", "comment": "Independent risk review passed"})
    assert approved.status_code == 200, approved.text
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    promoted = client.post(f"/api/v1/governance/models/{v1.id}/promote", headers=admin_headers)
    assert promoted.status_code == 200 and promoted.json()["state"] == "PROMOTED"

    v2 = _seed_promoted_model(db_session, creator, version="2.0.0")
    approved_v2 = client.post(f"/api/v1/governance/models/{v2.id}/decision", headers=reviewer_headers,
        json={"decision": "APPROVE", "comment": "Second version approved"})
    assert approved_v2.status_code == 200
    promoted_v2 = client.post(f"/api/v1/governance/models/{v2.id}/promote", headers=admin_headers)
    assert promoted_v2.status_code == 200
    assert db_session.get(ModelVersion, v1.id).state == "SUPERSEDED"
    rollback = client.post(f"/api/v1/governance/models/{v1.id}/rollback", headers=admin_headers)
    assert rollback.status_code == 200 and rollback.json()["state"] == "PROMOTED"
    assert db_session.get(ModelVersion, v2.id).state == "ROLLED_BACK"
    history = client.get(f"/api/v1/governance/models/{v1.id}/decisions", headers=admin_headers)
    assert history.status_code == 200 and len(history.json()) == 1


def test_paper_broker_idempotency_kill_switch_and_reconciliation(client, db_session) -> None:
    creator_email = "phase4.paper.creator@example.com"
    portfolio_email = "phase4.paper.portfolio@example.com"
    reviewer_email = "phase4.paper.reviewer@example.com"
    admin_email = "phase4.paper.admin@example.com"
    _register(client, creator_email); _add_role(db_session, creator_email, "QUANT_RESEARCHER")
    portfolio_token = _register(client, portfolio_email); _add_role(db_session, portfolio_email, "PORTFOLIO_ANALYST")
    reviewer_token = _register(client, reviewer_email); _add_role(db_session, reviewer_email, "RISK_REVIEWER")
    admin_token = _register(client, admin_email); _add_role(db_session, admin_email, "ADMIN")
    portfolio_token = client.post("/api/v1/auth/login", data={"username": portfolio_email, "password": "Strong-password-2026!"}).json()["access_token"]
    reviewer_token = client.post("/api/v1/auth/login", data={"username": reviewer_email, "password": "Strong-password-2026!"}).json()["access_token"]
    admin_token = client.post("/api/v1/auth/login", data={"username": admin_email, "password": "Strong-password-2026!"}).json()["access_token"]
    creator = db_session.scalar(select(User).where(User.email == creator_email))
    assert creator is not None
    db_session.add(Instrument(symbol="MSFT", name="Microsoft", exchange="NASDAQ", asset_type="EQUITY", currency="USD", is_active=True))
    db_session.commit()
    model = _seed_promoted_model(db_session, creator)
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    approved = client.post(f"/api/v1/governance/models/{model.id}/decision", headers=reviewer_headers,
        json={"decision": "APPROVE", "comment": "Approved for simulation"})
    assert approved.status_code == 200
    assert client.post(f"/api/v1/governance/models/{model.id}/promote", headers=admin_headers).status_code == 200

    portfolio_headers = {"Authorization": f"Bearer {portfolio_token}"}
    account_response = client.post("/api/v1/execution/accounts", headers=portfolio_headers, json={
        "name": "Phase 4 test paper portfolio", "initial_cash": "100000", "currency": "USD",
        "max_gross_exposure": 1.0, "max_symbol_exposure": 0.4,
        "max_order_notional": "25000", "fee_bps": 5, "slippage_bps": 5,
    })
    assert account_response.status_code == 201, account_response.text
    account_id = account_response.json()["id"]
    payload = {"client_order_id": "phase4-order-0001", "model_version_id": model.id,
        "symbol": "MSFT", "side": "BUY", "quantity": "10", "simulation_reference_price": "100"}
    first = client.post(f"/api/v1/execution/accounts/{account_id}/orders", headers=portfolio_headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "FILLED"
    assert Decimal(first.json()["fill_price"]) > Decimal("100")
    duplicate = client.post(f"/api/v1/execution/accounts/{account_id}/orders", headers=portfolio_headers, json=payload)
    assert duplicate.status_code == 201 and duplicate.json()["id"] == first.json()["id"]
    collision = client.post(f"/api/v1/execution/accounts/{account_id}/orders", headers=portfolio_headers,
        json=payload | {"quantity": "11"})
    assert collision.status_code == 409

    kill = client.post(f"/api/v1/execution/accounts/{account_id}/kill-switch", headers=admin_headers,
        json={"active": True, "reason": "Risk operator activated account halt"})
    assert kill.status_code == 200 and kill.json()["kill_switch"] is True
    blocked = client.post(f"/api/v1/execution/accounts/{account_id}/orders", headers=portfolio_headers,
        json=payload | {"client_order_id": "phase4-order-0002"})
    assert blocked.status_code == 201 and blocked.json()["status"] == "REJECTED"

    reconcile = client.post(f"/api/v1/execution/accounts/{account_id}/reconcile", headers=portfolio_headers,
        json={"repair": False})
    assert reconcile.status_code == 200 and reconcile.json()["consistent"] is True
    summary = client.get(f"/api/v1/execution/accounts/{account_id}/summary", headers=portfolio_headers)
    assert summary.status_code == 200
    assert len(summary.json()["positions"]) == 1
    history = client.get(f"/api/v1/execution/accounts/{account_id}/audit", headers=portfolio_headers)
    assert history.status_code == 200 and len(history.json()["fills"]) == 1
    assert db_session.scalar(select(PaperFill).where(PaperFill.order_id == first.json()["id"])) is not None
    assert db_session.scalar(select(PaperLedgerEntry).where(PaperLedgerEntry.account_id == account_id)) is not None


def test_paper_account_owner_scope_and_live_order_absence(client, db_session) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert not any("live" in path.lower() or "broker/live" in path.lower() for path in paths)
    assert "/api/v1/execution/accounts/{account_id}/orders" in paths
    assert "/api/v1/execution/accounts/{account_id}/reconcile" in paths


def test_rl_queue_is_idempotent_and_retryable(client, db_session, monkeypatch) -> None:
    from datetime import date
    from finsight.features.models import FeatureSetVersion
    from finsight.experiments.registry import configuration_sha256
    from finsight.market_data.models import DataSnapshot
    from finsight.infrastructure.database.models import JobRecord

    email = "phase4.rl.quant@example.com"
    token = _register(client, email); _add_role(db_session, email, "QUANT_RESEARCHER")
    token = client.post("/api/v1/auth/login", data={"username": email, "password": "Strong-password-2026!"}).json()["access_token"]
    user = db_session.scalar(select(User).where(User.email == email))
    snapshot = DataSnapshot(provider_key="manual_upload", instrument_symbol="MSFT", interval="1d",
        start_date=date(2022, 1, 1), end_date=date(2025, 1, 1), status="READY",
        file_path="/tmp/not-read-until-worker.parquet", storage_format="parquet", sha256="a" * 64,
        row_count=800, manifest={}, created_by=user.id)
    db_session.add(snapshot); db_session.flush()
    definition = {"features": ["return_1d"], "target": "next_day_return"}
    feature = FeatureSetVersion(feature_key="rl_test", version=1, description="test",
        definition=definition, source_snapshot_id=snapshot.id,
        definition_sha256=configuration_sha256(definition), created_by=user.id)
    db_session.add(feature); db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"idempotency_key": "phase4-rl-job-0001", "dataset_snapshot_id": snapshot.id,
        "feature_set_version_id": feature.id, "algorithm": "PPO", "total_timesteps": 5000}
    monkeypatch.setattr("app.api.v1.rl.enqueue_rl_evaluation", lambda job_id: (_ for _ in ()).throw(RuntimeError("redis down")))
    failed = client.post("/api/v1/rl/evaluations/jobs", headers=headers, json=payload)
    assert failed.status_code == 503
    job = db_session.scalar(select(JobRecord).where(JobRecord.idempotency_key == payload["idempotency_key"]))
    assert job is not None and job.status == "QUEUE_FAILED" and job.task_name == "rl.evaluate"
    collision = client.post("/api/v1/rl/evaluations/jobs", headers=headers,
        json=payload | {"algorithm": "SAC"})
    assert collision.status_code == 409
    monkeypatch.setattr("app.api.v1.jobs.enqueue_rl_evaluation", lambda job_id: None)
    retried = client.post(f"/api/v1/jobs/{job.id}/retry", headers=headers)
    assert retried.status_code == 202 and retried.json()["status"] == "QUEUED"
    replay = client.post("/api/v1/rl/evaluations/jobs", headers=headers, json=payload)
    assert replay.status_code == 202 and replay.json()["id"] == job.id


def test_rl_optional_training_provider_fails_clearly_without_extra() -> None:
    import importlib.util
    import numpy as np
    import pytest
    from finsight.reinforcement_learning.environments.portfolio_env import PortfolioTradingEnv
    from finsight.reinforcement_learning.evaluation.training import train_and_evaluate_rl

    with pytest.raises(ValueError, match="algorithm must be PPO or SAC"):
        train_and_evaluate_rl(np.linspace(100, 120, 150).tolist(), "A2C")
    if importlib.util.find_spec("gymnasium") is None or importlib.util.find_spec("stable_baselines3") is None:
        with pytest.raises(RuntimeError, match="Gymnasium is required"):
            PortfolioTradingEnv(np.linspace(100, 120, 150).tolist())
        with pytest.raises(RuntimeError, match="requires the 'rl' extra"):
            train_and_evaluate_rl(np.linspace(100, 120, 150).tolist(), "PPO")


def test_paper_reconciliation_repairs_quantity_cash_and_ledger(client, db_session) -> None:
    # Reuse the complete approval->promotion->fill journey, then deliberately corrupt derived balances.
    creator_email = "phase4.repair.creator@example.com"
    portfolio_email = "phase4.repair.portfolio@example.com"
    reviewer_email = "phase4.repair.reviewer@example.com"
    admin_email = "phase4.repair.admin@example.com"
    _register(client, creator_email); _add_role(db_session, creator_email, "QUANT_RESEARCHER")
    ptoken = _register(client, portfolio_email); _add_role(db_session, portfolio_email, "PORTFOLIO_ANALYST")
    rtoken = _register(client, reviewer_email); _add_role(db_session, reviewer_email, "RISK_REVIEWER")
    atoken = _register(client, admin_email); _add_role(db_session, admin_email, "ADMIN")
    ptoken = client.post("/api/v1/auth/login", data={"username": portfolio_email, "password": "Strong-password-2026!"}).json()["access_token"]
    rtoken = client.post("/api/v1/auth/login", data={"username": reviewer_email, "password": "Strong-password-2026!"}).json()["access_token"]
    atoken = client.post("/api/v1/auth/login", data={"username": admin_email, "password": "Strong-password-2026!"}).json()["access_token"]
    creator = db_session.scalar(select(User).where(User.email == creator_email))
    db_session.add(Instrument(symbol="MSFT", name="Microsoft", exchange="NASDAQ", asset_type="EQUITY", currency="USD", is_active=True))
    db_session.commit()
    model = _seed_promoted_model(db_session, creator, key="repair-model")
    assert client.post(f"/api/v1/governance/models/{model.id}/decision", headers={"Authorization": f"Bearer {rtoken}"},
        json={"decision": "APPROVE", "comment": "approve"}).status_code == 200
    assert client.post(f"/api/v1/governance/models/{model.id}/promote", headers={"Authorization": f"Bearer {atoken}"}).status_code == 200
    ph = {"Authorization": f"Bearer {ptoken}"}
    account = client.post("/api/v1/execution/accounts", headers=ph, json={"name": "Repair ledger", "initial_cash": "10000"}).json()
    order = client.post(f"/api/v1/execution/accounts/{account['id']}/orders", headers=ph, json={
        "client_order_id": "repair-order-0001", "model_version_id": model.id, "symbol": "MSFT",
        "side": "BUY", "quantity": "10", "simulation_reference_price": "100"}).json()
    position = db_session.scalar(select(PaperPosition).where(PaperPosition.account_id == account["id"]))
    account_row = db_session.get(PaperAccount, account["id"])
    position.quantity = Decimal("9")
    account_row.cash_balance = Decimal(account_row.cash_balance) + Decimal("20")
    ledger = db_session.scalar(select(PaperLedgerEntry).where(PaperLedgerEntry.account_id == account["id"]))
    ledger.cash_delta = Decimal(ledger.cash_delta) + Decimal("1")
    db_session.commit()
    before = client.post(f"/api/v1/execution/accounts/{account['id']}/reconcile", headers=ph, json={"repair": False})
    assert before.status_code == 200 and before.json()["consistent"] is False
    repaired = client.post(f"/api/v1/execution/accounts/{account['id']}/reconcile",
        headers={"Authorization": f"Bearer {atoken}"}, json={"repair": True})
    assert repaired.status_code == 200 and repaired.json()["consistent"] is True and repaired.json()["repaired"] is True
    position = db_session.scalar(select(PaperPosition).where(PaperPosition.account_id == account["id"]))
    assert position.quantity == Decimal("10.00000000")
