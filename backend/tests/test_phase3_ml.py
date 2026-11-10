"""Phase 3 reproducible model and sentiment baseline tests."""
import numpy as np
import pandas as pd
import pytest

from finsight.models.sentiment import score_financial_sentiment
from finsight.models.supervised import train_supervised_evaluation, configuration_fingerprint


def sample_frame(rows: int = 180) -> pd.DataFrame:
    rng = np.random.default_rng(23)
    x = rng.normal(size=rows)
    z = rng.normal(size=rows)
    y = 0.65 * x - 0.25 * z + rng.normal(scale=0.08, size=rows)
    return pd.DataFrame({"date": pd.bdate_range("2022-01-03", periods=rows),
                         "momentum_5d": x, "volatility_20d": z, "next_day_return": y})


def test_ridge_evaluation_uses_chronological_holdout_and_returns_metrics() -> None:
    frame = sample_frame()
    result = train_supervised_evaluation(frame, ["momentum_5d", "volatility_20d"],
        "next_day_return", model_family="ridge", random_seed=7)
    assert result.configuration["split_method"] == "chronological_no_shuffle"
    assert result.train_rows == 144
    assert result.test_rows == 36
    assert result.metrics["test_start"] == frame.iloc[144]["date"].date().isoformat()
    assert result.metrics["test_end"] == frame.iloc[-1]["date"].date().isoformat()
    assert 0 <= result.metrics["directional_accuracy"] <= 1
    assert np.isfinite(result.metrics["rmse"])


def test_ml_evaluation_rejects_target_feature_leakage_and_invalid_rows() -> None:
    frame = sample_frame()
    with pytest.raises(ValueError, match="target cannot be a feature"):
        train_supervised_evaluation(frame, ["momentum_5d", "next_day_return"], "next_day_return")
    with pytest.raises(ValueError, match="At least 60"):
        train_supervised_evaluation(frame.head(20), ["momentum_5d"], "next_day_return")


def test_financial_sentiment_is_transparent_and_handles_negation() -> None:
    positive = score_financial_sentiment("Revenue growth beat estimates and profits improved")
    negative = score_financial_sentiment("Revenue declined and management cut the outlook")
    negated = score_financial_sentiment("Revenue did not decline")
    assert positive["label"] == "POSITIVE"
    assert negative["label"] == "NEGATIVE"
    assert negated["label"] == "POSITIVE"
    assert positive["pretrained_model"] is False
    assert positive["method"] == "transparent_lexicon_v1"


def test_configuration_fingerprint_is_order_stable() -> None:
    assert configuration_fingerprint({"a": 1, "b": 2}) == configuration_fingerprint({"b": 2, "a": 1})

@pytest.mark.parametrize("model_family,package", [("xgboost", "xgboost"), ("lightgbm", "lightgbm")])
def test_gradient_boosting_families_run_chronological_holdout(model_family: str, package: str) -> None:
    pytest.importorskip(package)
    result = train_supervised_evaluation(sample_frame(140), ["momentum_5d", "volatility_20d"],
        "next_day_return", model_family=model_family, random_seed=11)
    assert result.configuration["model_family"] == model_family
    assert result.configuration["split_method"] == "chronological_no_shuffle"
    assert result.test_rows == 28
    assert np.isfinite(result.metrics["rmse"])


def test_pytorch_lstm_uses_training_only_scaler_and_chronological_test() -> None:
    pytest.importorskip("torch")
    from finsight.models.supervised import train_lstm_evaluation
    result = train_lstm_evaluation(sample_frame(150), ["momentum_5d", "volatility_20d"],
        "next_day_return", random_seed=5, test_fraction=0.2, sequence_length=5, epochs=5)
    assert result.configuration["model_family"] == "lstm"
    assert result.configuration["split_method"] == "chronological_no_shuffle"
    assert len(result.configuration["scaler_mean"]) == 2
    assert result.test_rows >= 10
    assert np.isfinite(result.metrics["rmse"])


def test_ml_api_pins_feature_set_and_snapshot_and_persists_model_artifact(client, db_session, tmp_path, monkeypatch) -> None:
    import hashlib
    from datetime import date
    from types import SimpleNamespace
    from sqlalchemy import select
    from app.models.entities import DataSnapshot, Role, User
    from finsight.features.models import FeatureSetVersion
    from finsight.experiments.registry import configuration_sha256
    from finsight.documents.models import ModelEvaluation
    import app.api.v1.ml as ml_api

    email = "phase3.ml.quant@example.com"
    client.post("/api/v1/auth/register", json={
        "email": email, "full_name": "ML Quant", "password": "A-strong-password-2026",
    })
    user = db_session.scalar(select(User).where(User.email == email))
    role = db_session.scalar(select(Role).where(Role.key == "QUANT_RESEARCHER"))
    assert user is not None and role is not None
    user.roles.append(role)
    raw_path = tmp_path / "snapshot.parquet"
    raw_path.write_bytes(b"test snapshot payload")
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    snapshot = DataSnapshot(provider_key="manual_upload", instrument_symbol="MSFT", interval="1d",
        start_date=date(2022, 1, 3), end_date=date(2022, 9, 9), status="READY",
        file_path=str(raw_path), storage_format="parquet", sha256=digest, row_count=180,
        manifest={}, created_by=user.id)
    db_session.add(snapshot)
    db_session.flush()
    definition = {"features": ["return_1d", "momentum_5d"], "target": "next_day_return"}
    feature_set = FeatureSetVersion(feature_key="phase3_ml_features", version=1,
        description="Test declared features", definition=definition,
        source_snapshot_id=snapshot.id, definition_sha256=configuration_sha256(definition),
        created_by=user.id)
    db_session.add(feature_set)
    db_session.commit()
    idx = np.arange(180, dtype=float)
    close = 100 + 0.08 * idx + np.sin(idx / 6)
    raw = pd.DataFrame({"date": pd.bdate_range("2022-01-03", periods=180),
        "open": close * 0.999, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1_000_000 + idx * 5})
    monkeypatch.setattr(ml_api.pd, "read_parquet", lambda path: raw.copy())
    monkeypatch.setattr(ml_api, "get_settings", lambda: SimpleNamespace(
        data_storage_path=str(tmp_path / "artifacts"), max_ml_evaluation_rows=100000))
    token = client.post("/api/v1/auth/login", data={
        "username": email, "password": "A-strong-password-2026",
    }).json()["access_token"]
    response = client.post("/api/v1/ml/evaluations", headers={"Authorization": f"Bearer {token}"}, json={
        "dataset_snapshot_id": snapshot.id, "feature_set_version_id": feature_set.id,
        "model_family": "ridge", "random_seed": 42, "test_fraction": 0.2,
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["feature_set_version_id"] == feature_set.id
    assert body["target_column"] == "target_next_day_return"
    assert body["feature_columns"] == definition["features"]
    assert body["configuration"]["dataset_sha256"] == digest
    assert len(body["configuration_sha256"]) == 64
    assert (tmp_path / "artifacts" / body["artifact_path"]).exists()
    stored = db_session.get(ModelEvaluation, body["id"])
    assert stored is not None and stored.status == "SUCCEEDED"
    comparison = client.get(
        f"/api/v1/ml/evaluations/compare?snapshot_id={snapshot.id}&feature_set_version_id={feature_set.id}",
        headers={"Authorization": f"Bearer {token}"})
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["comparison_count"] == 1
    assert comparison.json()["ranked_by_rmse"][0]["id"] == body["id"]


def test_ml_api_rejects_feature_set_from_a_different_snapshot(client, db_session) -> None:
    import hashlib
    from datetime import date
    from sqlalchemy import select
    from app.models.entities import DataSnapshot, Role, User
    from finsight.features.models import FeatureSetVersion
    from finsight.experiments.registry import configuration_sha256

    email = "phase3.ml.lineage@example.com"
    client.post("/api/v1/auth/register", json={
        "email": email, "full_name": "ML Lineage", "password": "A-strong-password-2026",
    })
    user = db_session.scalar(select(User).where(User.email == email))
    role = db_session.scalar(select(Role).where(Role.key == "QUANT_RESEARCHER"))
    assert user is not None and role is not None
    user.roles.append(role)
    snapshots = [DataSnapshot(provider_key="manual_upload", instrument_symbol=symbol, interval="1d",
        start_date=date(2022, 1, 3), end_date=date(2022, 9, 9), status="READY",
        file_path="/tmp/not-read.parquet", storage_format="parquet", sha256=hashlib.sha256(symbol.encode()).hexdigest(),
        row_count=180, manifest={}, created_by=user.id) for symbol in ["MSFT", "SPY"]]
    db_session.add_all(snapshots)
    db_session.flush()
    definition = {"features": ["return_1d"], "target": "next_day_return"}
    feature_set = FeatureSetVersion(feature_key="lineage", version=1, description="Lineage check",
        definition=definition, source_snapshot_id=snapshots[1].id,
        definition_sha256=configuration_sha256(definition), created_by=user.id)
    db_session.add(feature_set)
    db_session.commit()
    token = client.post("/api/v1/auth/login", data={
        "username": email, "password": "A-strong-password-2026",
    }).json()["access_token"]
    response = client.post("/api/v1/ml/evaluations", headers={"Authorization": f"Bearer {token}"}, json={
        "dataset_snapshot_id": snapshots[0].id, "feature_set_version_id": feature_set.id,
        "model_family": "ridge",
    })
    assert response.status_code == 422
    assert "derived from the selected dataset" in response.json()["detail"]


def test_finbert_adapter_returns_model_probabilities_without_loading_external_weights() -> None:
    import torch
    from types import SimpleNamespace
    from finsight.models.sentiment import score_finbert_sentiment

    class StubTokenizer:
        def __call__(self, text, **kwargs):
            assert kwargs["max_length"] == 512
            return {"input_ids": torch.tensor([[1, 2, 3]])}

    class StubModel:
        config = SimpleNamespace(id2label={0: "positive", 1: "negative", 2: "neutral"})
        def __call__(self, **kwargs):
            return SimpleNamespace(logits=torch.tensor([[4.0, 0.5, 0.1]]))

    result = score_finbert_sentiment("Revenue growth was strong", tokenizer=StubTokenizer(), model=StubModel())
    assert result["label"] == "POSITIVE"
    assert result["method"] == "finbert_pretrained_v1"
    assert result["pretrained_model"] is True
    assert abs(sum(result["probabilities"].values()) - 1.0) < 1e-6


def test_finbert_adapter_rejects_empty_or_oversized_text() -> None:
    from finsight.models.sentiment import score_finbert_sentiment
    with pytest.raises(ValueError, match="cannot be empty"):
        score_finbert_sentiment(" ")
    with pytest.raises(ValueError, match="20,000"):
        score_finbert_sentiment("x" * 20_001)


def test_finbert_api_provider_is_explicit_and_returns_pretrained_metadata(client, monkeypatch) -> None:
    import app.api.v1.ml as ml_api
    client.post("/api/v1/auth/register", json={
        "email": "phase3.finbert.api@example.com", "full_name": "Sentiment Analyst",
        "password": "A-strong-password-2026",
    })
    token = client.post("/api/v1/auth/login", data={
        "username": "phase3.finbert.api@example.com", "password": "A-strong-password-2026",
    }).json()["access_token"]
    monkeypatch.setattr(ml_api, "score_finbert_sentiment", lambda text: {
        "label": "POSITIVE", "score": 0.85, "probabilities": {"positive": 0.9, "negative": 0.05, "neutral": 0.05},
        "method": "finbert_pretrained_v1", "model_name": "ProsusAI/finbert", "pretrained_model": True,
    })
    response = client.post("/api/v1/ml/sentiment", headers={"Authorization": f"Bearer {token}"},
        json={"text": "Revenue growth beat expectations", "provider": "finbert"})
    assert response.status_code == 200, response.text
    assert response.json()["pretrained_model"] is True
    assert response.json()["model_name"] == "ProsusAI/finbert"


def test_ml_evaluation_can_be_queued_with_owner_idempotency(client, db_session, monkeypatch) -> None:
    from sqlalchemy import select
    from app.api.v1 import ml as ml_api
    from app.models.entities import Role, User
    from finsight.infrastructure.database.models import JobRecord

    email = "phase3.ml.queue@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "full_name": "Queued Quant",
        "password": "A-strong-password-2026"})
    user = db_session.scalar(select(User).where(User.email == email))
    role = db_session.scalar(select(Role).where(Role.key == "QUANT_RESEARCHER"))
    assert user is not None and role is not None
    user.roles.append(role)
    db_session.commit()
    token = client.post("/api/v1/auth/login", data={"username": email,
        "password": "A-strong-password-2026"}).json()["access_token"]
    dispatched = []
    monkeypatch.setattr(ml_api, "enqueue_model_evaluation", lambda job_id: dispatched.append(job_id))
    payload = {"dataset_snapshot_id": "snapshot-pending-validation", "feature_set_version_id": "feature-pending-validation",
        "model_family": "ridge", "idempotency_key": "ml-evaluation-once-001"}
    first = client.post("/api/v1/ml/evaluations/jobs", headers={"Authorization": f"Bearer {token}"}, json=payload)
    second = client.post("/api/v1/ml/evaluations/jobs", headers={"Authorization": f"Bearer {token}"}, json=payload)
    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["id"] == second.json()["id"]
    assert dispatched == [first.json()["id"]]
    stored = db_session.get(JobRecord, first.json()["id"])
    assert stored is not None and stored.task_name == "ml.evaluate"
    assert stored.payload["model_family"] == "ridge"
