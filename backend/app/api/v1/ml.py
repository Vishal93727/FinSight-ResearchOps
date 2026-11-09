"""Reproducible supervised ML evaluation endpoints for READY market snapshots."""
from __future__ import annotations
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from finsight.core.config import get_settings
from finsight.core.security import get_current_user, require_roles
from finsight.documents.models import ModelEvaluation
from finsight.identity.models import User
from finsight.infrastructure.database.session import get_db
from finsight.infrastructure.database.models import JobRecord
from finsight.market_data.models import DataSnapshot
from finsight.features.models import FeatureSetVersion
from finsight.features.engineering import build_declared_feature_frame
from finsight.experiments.registry import configuration_sha256
from finsight.models.sentiment import score_financial_sentiment, score_finbert_sentiment
from finsight.models.supervised import train_supervised_evaluation, train_lstm_evaluation, configuration_fingerprint
from app.schemas.ml import ModelEvaluationCreate, ModelEvaluationJobCreate, ModelEvaluationResponse, SentimentRequest
from app.schemas.jobs import JobResponse
from app.services.audit import record_audit
from app.services.jobs import enqueue_model_evaluation

router = APIRouter(prefix="/ml", tags=["advanced ML"])


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


@router.post("/evaluations", response_model=ModelEvaluationResponse, status_code=201)
def create_model_evaluation(payload: ModelEvaluationCreate, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    snapshot = db.get(DataSnapshot, payload.dataset_snapshot_id)
    if snapshot is None or snapshot.status != "READY":
        raise HTTPException(status_code=422, detail="A READY market-data snapshot is required")
    if snapshot.storage_format.lower() != "parquet":
        raise HTTPException(status_code=422, detail="Model evaluation requires a Parquet snapshot")
    feature_set = db.get(FeatureSetVersion, payload.feature_set_version_id)
    if feature_set is None:
        raise HTTPException(status_code=404, detail="Feature-set version not found")
    if feature_set.source_snapshot_id != snapshot.id:
        raise HTTPException(status_code=422, detail="Feature set must be derived from the selected dataset snapshot")
    if configuration_sha256(feature_set.definition) != feature_set.definition_sha256:
        raise HTTPException(status_code=409, detail="Feature-set definition fingerprint mismatch")
    try:
        if _hash_file(snapshot.file_path) != snapshot.sha256:
            raise HTTPException(status_code=409, detail="Snapshot hash does not match its immutable manifest")
        raw_frame = pd.read_parquet(snapshot.file_path)
        if len(raw_frame) > get_settings().max_ml_evaluation_rows:
            raise HTTPException(status_code=413, detail="Snapshot exceeds the configured ML evaluation row limit")
        frame = build_declared_feature_frame(raw_frame, feature_set.definition)
    except HTTPException: raise
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Feature engineering failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Snapshot could not be read as Parquet") from exc
    feature_columns = list(feature_set.definition["features"])
    target_column = "target_next_day_return"
    settings = get_settings()
    if len(frame) > settings.max_ml_evaluation_rows:
        raise HTTPException(status_code=413, detail="Snapshot exceeds the configured ML evaluation row limit")
    try:
        if payload.model_family == "lstm":
            evaluation = train_lstm_evaluation(frame, feature_columns, target_column,
                payload.date_column, payload.random_seed, payload.test_fraction, payload.sequence_length, payload.epochs)
        else:
            evaluation = train_supervised_evaluation(frame, feature_columns, target_column,
                payload.date_column, payload.model_family, payload.random_seed, payload.test_fraction)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    configuration = evaluation.configuration | {"queued_job_id": getattr(request.state, "job_id", None),
        "dataset_snapshot_id": snapshot.id,
        "dataset_sha256": snapshot.sha256, "feature_set_version_id": feature_set.id,
        "feature_definition_sha256": feature_set.definition_sha256,
        "target_horizon_note": "target_next_day_return is shifted one session forward by the feature pipeline."}
    fingerprint = configuration_fingerprint(configuration)
    artifact_dir = Path(settings.data_storage_path).resolve() / "ml_evaluations" / snapshot.id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{fingerprint}.joblib"
    metrics_path = artifact_dir / f"{fingerprint}.metrics.json"
    try:
        import joblib
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="ML artifact persistence requires the ml optional dependencies") from exc
    if payload.model_family == "lstm":
        import torch
        torch.save({"state_dict": evaluation.model.state_dict(), "configuration": configuration}, artifact_path.with_suffix(".pt"))
        artifact_path = artifact_path.with_suffix(".pt")
    else:
        joblib.dump(evaluation.model, artifact_path)
    metrics_path.write_text(json.dumps(evaluation.metrics, sort_keys=True, allow_nan=False, indent=2), encoding="utf-8")
    record = ModelEvaluation(dataset_snapshot_id=snapshot.id, instrument_symbol=snapshot.instrument_symbol,
        model_family=payload.model_family, target_column=target_column,
        feature_set_version_id=feature_set.id, feature_columns=feature_columns, configuration=configuration,
        configuration_sha256=fingerprint, metrics=evaluation.metrics,
        artifact_path=str(artifact_path.relative_to(Path(settings.data_storage_path).resolve())), status="SUCCEEDED", created_by=user.id)
    db.add(record); db.flush()
    record_audit(db, actor=user, action="ml.supervised_evaluation_completed", resource_type="model_evaluation",
        resource_id=record.id, request_id=getattr(request.state, "request_id", None),
        details={"model_family": payload.model_family, "configuration_sha256": fingerprint,
                 "dataset_snapshot_id": snapshot.id})
    db.commit(); db.refresh(record)
    return record


@router.post("/evaluations/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def queue_model_evaluation(payload: ModelEvaluationJobCreate, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    values = payload.model_dump(exclude={"idempotency_key"})
    if payload.idempotency_key:
        existing = db.scalar(select(JobRecord).where(JobRecord.created_by == user.id,
            JobRecord.idempotency_key == payload.idempotency_key))
        if existing is not None:
            if existing.task_name != "ml.evaluate" or (existing.payload or {}) != values:
                raise HTTPException(status_code=409, detail="This idempotency key was already used for a different job")
            return existing
    job = JobRecord(task_name="ml.evaluate", status="QUEUED", payload=values,
        idempotency_key=payload.idempotency_key, created_by=user.id)
    db.add(job); db.flush()
    record_audit(db, actor=user, action="ml.evaluation_queued", resource_type="job",
        resource_id=job.id, request_id=getattr(request.state, "request_id", None),
        details={"dataset_snapshot_id": payload.dataset_snapshot_id,
                 "feature_set_version_id": payload.feature_set_version_id,
                 "model_family": payload.model_family})
    db.commit(); db.refresh(job)
    try:
        enqueue_model_evaluation(job.id)
    except Exception as exc:
        job.status = "QUEUE_FAILED"
        job.error_message = "Model evaluation queue is unavailable; retry after checking Redis and worker status"
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail=job.error_message) from exc
    return job


@router.get("/evaluations", response_model=list[ModelEvaluationResponse])
def list_model_evaluations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(ModelEvaluation).order_by(ModelEvaluation.created_at.desc()).limit(200)).all())


@router.post("/sentiment")
def financial_sentiment_baseline(payload: SentimentRequest,
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER"))):
    if payload.provider == "finbert":
        try:
            return score_finbert_sentiment(payload.text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return score_financial_sentiment(payload.text)


@router.get("/evaluations/compare")
def compare_model_evaluations(snapshot_id: str = Query(min_length=1, max_length=36),
    feature_set_version_id: str = Query(min_length=1, max_length=36),
    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Compare completed model evaluations on the exact same pinned data/feature lineage."""
    snapshot = db.get(DataSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Dataset snapshot not found")
    feature_set = db.get(FeatureSetVersion, feature_set_version_id)
    if feature_set is None:
        raise HTTPException(status_code=404, detail="Feature-set version not found")
    if feature_set.source_snapshot_id != snapshot_id:
        raise HTTPException(status_code=422, detail="Feature set must be derived from the selected dataset snapshot")
    statement = select(ModelEvaluation).where(
        ModelEvaluation.dataset_snapshot_id == snapshot_id,
        ModelEvaluation.feature_set_version_id == feature_set_version_id,
        ModelEvaluation.status == "SUCCEEDED"
    )
    records = list(db.scalars(statement.order_by(ModelEvaluation.created_at.desc()).limit(100)).all())
    rows = [{"id": item.id, "instrument_symbol": item.instrument_symbol,
        "feature_set_version_id": item.feature_set_version_id, "model_family": item.model_family,
        "metrics": item.metrics, "configuration_sha256": item.configuration_sha256,
        "created_at": item.created_at.isoformat()} for item in records]
    rows.sort(key=lambda row: (float(row["metrics"].get("rmse", float("inf"))), row["model_family"]))
    best_directional = max(rows, key=lambda row: float(row["metrics"].get("directional_accuracy", -1)), default=None)
    return {"dataset_snapshot_id": snapshot_id, "instrument_symbol": snapshot.instrument_symbol,
        "feature_set_version_id": feature_set_version_id, "comparison_count": len(rows),
        "ranking_metric": "rmse_ascending", "ranked_by_rmse": rows,
        "best_directional_accuracy_evaluation_id": best_directional["id"] if best_directional else None,
        "interpretation_note": "Model prediction metrics are not strategy returns and do not establish investment performance."}
