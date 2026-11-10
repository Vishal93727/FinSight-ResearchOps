"""Shared validation and training service for queued PPO/SAC evaluation jobs."""
from __future__ import annotations
import hashlib
from pathlib import Path
import pandas as pd
from sqlalchemy.orm import Session
from finsight.core.config import get_settings
from finsight.governance.models import RLPolicyEvaluation
from finsight.market_data.models import DataSnapshot
from finsight.features.models import FeatureSetVersion
from finsight.experiments.registry import configuration_sha256
from finsight.reinforcement_learning.evaluation.training import train_and_evaluate_rl
from finsight.features.engineering import build_declared_feature_frame


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def align_rl_observations(frame: pd.DataFrame, definition: dict) -> tuple[list[float], object, list[str]]:
    """Build point-in-time declared features and align them to the same close prices."""
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError("The selected snapshot must contain canonical OHLCV columns")
    ordered = frame.sort_values("date", kind="stable").reset_index(drop=True).copy()
    feature_frame = build_declared_feature_frame(ordered, definition)
    feature_names = list(definition["features"])
    raw_prices = ordered.copy()
    raw_prices["_join_date"] = pd.to_datetime(raw_prices["date"], errors="raise", utc=True)
    feature_frame["_join_date"] = pd.to_datetime(feature_frame["date"], errors="raise", utc=True)
    aligned = feature_frame.merge(
        raw_prices[["_join_date", "close"]], on="_join_date", how="left", validate="one_to_one"
    )
    if aligned.empty or aligned["close"].isna().any():
        raise ValueError("RL features could not be aligned to the source close-price series")
    prices = pd.to_numeric(aligned["close"], errors="coerce").astype(float).tolist()
    feature_values = aligned[feature_names].to_numpy(dtype=float)
    if len(prices) < 120:
        raise ValueError("At least 120 aligned feature/price observations are required for RL evaluation")
    return prices, feature_values, feature_names


def run_rl_evaluation(db: Session, *, user_id: str, payload: dict) -> RLPolicyEvaluation:
    snapshot = db.get(DataSnapshot, payload["dataset_snapshot_id"])
    if snapshot is None or snapshot.status != "READY" or snapshot.storage_format.lower() != "parquet":
        raise ValueError("A READY Parquet market-data snapshot is required for RL evaluation")
    feature_set = db.get(FeatureSetVersion, payload["feature_set_version_id"])
    if feature_set is None or feature_set.source_snapshot_id != snapshot.id:
        raise ValueError("Feature-set version must be derived from the selected dataset snapshot")
    if configuration_sha256(feature_set.definition) != feature_set.definition_sha256:
        raise ValueError("Feature-set definition fingerprint mismatch")
    if _sha256(snapshot.file_path) != snapshot.sha256:
        raise ValueError("Market-data snapshot SHA-256 does not match its immutable manifest")
    frame = pd.read_parquet(snapshot.file_path)
    date_column, price_column = payload.get("date_column", "date"), payload.get("price_column", "close")
    if date_column != "date" or price_column != "close":
        raise ValueError("RL uses the canonical date and close columns so feature and price lineage remain aligned")
    prices, feature_values, feature_names = align_rl_observations(frame, feature_set.definition)
    settings = get_settings()
    output_dir = Path(settings.data_storage_path).resolve() / "rl_evaluations" / snapshot.id
    result = train_and_evaluate_rl(prices, payload["algorithm"], seed=payload.get("seed", 42),
        total_timesteps=payload.get("total_timesteps", 20000), train_fraction=payload.get("train_fraction", 0.70),
        fee_bps=payload.get("fee_bps", 5.0), slippage_bps=payload.get("slippage_bps", 5.0),
        features=feature_values, feature_names=feature_names, artifact_dir=output_dir)
    artifact_uri = None
    artifact_hash = None
    if result.get("artifact_path"):
        artifact = Path(result["artifact_path"]).resolve()
        artifact_uri = str(artifact.relative_to(Path(settings.data_storage_path).resolve()))
        artifact_hash = _sha256(str(artifact))
    evaluation = RLPolicyEvaluation(algorithm=result["algorithm"], dataset_snapshot_id=snapshot.id,
        feature_set_version_id=feature_set.id, configuration=result["configuration"] | {
            "queued_job_id": payload.get("_queued_job_id"),
            "dataset_sha256": snapshot.sha256, "feature_definition_sha256": feature_set.definition_sha256,
            "instrument_symbol": snapshot.instrument_symbol},
        configuration_sha256=result["configuration_sha256"], metrics=result["metrics"],
        artifact_uri=artifact_uri, artifact_sha256=artifact_hash, status="SUCCEEDED",
        out_of_sample=bool(result["out_of_sample"]), created_by=user_id)
    db.add(evaluation)
    db.flush()
    return evaluation
