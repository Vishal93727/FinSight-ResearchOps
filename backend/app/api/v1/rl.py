"""Queued PPO/SAC training and same-lineage RL evaluation comparisons."""
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from finsight.core.security import require_roles
from finsight.governance.models import RLPolicyEvaluation
from finsight.identity.models import User
from finsight.infrastructure.database.models import JobRecord
from finsight.infrastructure.database.session import get_db
from finsight.market_data.models import DataSnapshot
from finsight.features.models import FeatureSetVersion
from app.schemas.phase4 import RLEvaluationJobCreate
from app.schemas.jobs import JobResponse
from app.services.audit import record_audit
from app.services.jobs import enqueue_rl_evaluation

router = APIRouter(prefix="/rl", tags=["reinforcement learning"])


@router.post("/evaluations/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def queue_rl_evaluation(payload: RLEvaluationJobCreate, request: Request,
                        db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    snapshot = db.get(DataSnapshot, payload.dataset_snapshot_id)
    if snapshot is None or snapshot.status != "READY" or snapshot.storage_format.lower() != "parquet":
        raise HTTPException(status_code=422, detail="A READY Parquet market-data snapshot is required")
    feature = db.get(FeatureSetVersion, payload.feature_set_version_id)
    if feature is None or feature.source_snapshot_id != snapshot.id:
        raise HTTPException(status_code=422, detail="Feature set must be derived from the selected snapshot")
    values = payload.model_dump(exclude={"idempotency_key"})
    existing = db.scalar(select(JobRecord).where(JobRecord.created_by == user.id,
        JobRecord.idempotency_key == payload.idempotency_key))
    if existing:
        if existing.task_name != "rl.evaluate" or existing.payload != values:
            raise HTTPException(status_code=409, detail="Idempotency key is already used for a different job")
        return existing
    job = JobRecord(task_name="rl.evaluate", status="QUEUED", payload=values,
        idempotency_key=payload.idempotency_key, created_by=user.id)
    db.add(job); db.flush()
    record_audit(db, actor=user, action="rl.evaluation_queued", resource_type="job", resource_id=job.id,
        request_id=getattr(request.state, "request_id", None), details={"algorithm": payload.algorithm})
    db.commit(); db.refresh(job)
    try:
        enqueue_rl_evaluation(job.id)
    except Exception as exc:
        job.status = "QUEUE_FAILED"
        job.error_message = "Background queue is unavailable; retry after checking Redis and Celery worker status"
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail=job.error_message) from exc
    return job


@router.get("/evaluations")
def list_rl_evaluations(limit: int = 100, db: Session = Depends(get_db),
                        user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "RESEARCH_ANALYST", "READ_ONLY_VIEWER"))):
    return db.scalars(select(RLPolicyEvaluation).order_by(RLPolicyEvaluation.created_at.desc()).limit(max(1, min(limit, 300)))).all()


@router.get("/evaluations/comparison")
def compare_rl_evaluations(dataset_snapshot_id: str, feature_set_version_id: str,
                          db: Session = Depends(get_db), user: User = Depends(require_roles(
                              "ADMIN", "QUANT_RESEARCHER", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "RESEARCH_ANALYST", "READ_ONLY_VIEWER"))):
    items = db.scalars(select(RLPolicyEvaluation).where(
        RLPolicyEvaluation.dataset_snapshot_id == dataset_snapshot_id,
        RLPolicyEvaluation.feature_set_version_id == feature_set_version_id,
        RLPolicyEvaluation.status == "SUCCEEDED", RLPolicyEvaluation.out_of_sample.is_(True)
    ).order_by(RLPolicyEvaluation.created_at.desc())).all()
    return [{"id": item.id, "algorithm": item.algorithm, "metrics": item.metrics,
        "configuration": item.configuration, "configuration_sha256": item.configuration_sha256,
        "artifact_uri": item.artifact_uri, "artifact_sha256": item.artifact_sha256,
        "dataset_snapshot_id": item.dataset_snapshot_id,
        "feature_set_version_id": item.feature_set_version_id,
        "out_of_sample": item.out_of_sample} for item in items]
