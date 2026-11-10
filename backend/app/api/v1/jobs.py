"""Create and inspect background jobs."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight.core.security import get_current_user
from finsight.infrastructure.database.session import get_db
from finsight.infrastructure.database.models import JobRecord
from finsight.identity.models import User
from app.schemas.jobs import JobCreateRequest, JobResponse
from app.services.audit import record_audit
from app.services.jobs import (
    enqueue_system_ping, enqueue_document_ingestion, enqueue_model_evaluation, enqueue_research_ask, enqueue_rl_evaluation,
)

router = APIRouter(prefix="/jobs", tags=["background jobs"])


@router.get("", response_model=list[JobResponse])
def list_jobs(limit: int = 50, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> list[JobRecord]:
    limit = max(1, min(limit, 100))
    statement = select(JobRecord).order_by(JobRecord.created_at.desc()).limit(limit)
    if "ADMIN" not in {role.key for role in user.roles}:
        statement = statement.where(JobRecord.created_by == user.id)
    return list(db.scalars(statement).all())


@router.post("/ping", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_ping_job(
    payload: JobCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRecord:
    if payload.idempotency_key:
        existing = db.scalar(
            select(JobRecord).where(
                JobRecord.created_by == user.id,
                JobRecord.idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
    job = JobRecord(
        task_name="system.ping",
        status="QUEUED",
        payload={},
        idempotency_key=payload.idempotency_key,
        created_by=user.id,
    )
    db.add(job)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="jobs.job_queued",
        resource_type="job",
        resource_id=job.id,
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    db.refresh(job)
    try:
        enqueue_system_ping(job.id)
    except Exception as exc:
        job.status = "QUEUE_FAILED"
        job.error_message = "Background queue is unavailable; retry after checking Redis and worker status"
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail=job.error_message) from exc
    return job


@router.post("/{job_id}/retry", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_queued_job(job_id: str, request: Request, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> JobRecord:
    job = db.get(JobRecord, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    role_keys = {role.key for role in user.roles}
    if job.created_by != user.id and "ADMIN" not in role_keys:
        raise HTTPException(status_code=403, detail="You cannot retry this job")
    if job.status != "QUEUE_FAILED":
        raise HTTPException(status_code=409, detail="Only jobs that failed to dispatch can be retried")
    dispatchers = {"system.ping": enqueue_system_ping,
        "documents.ingest": enqueue_document_ingestion,
        "ml.evaluate": enqueue_model_evaluation,
        "research.ask": enqueue_research_ask, "rl.evaluate": enqueue_rl_evaluation}
    dispatcher = dispatchers.get(job.task_name)
    if dispatcher is None:
        raise HTTPException(status_code=422, detail="This job type does not support queue retry")
    job.status = "QUEUED"
    job.error_message = None
    job.completed_at = None
    db.commit()
    db.refresh(job)
    try:
        dispatcher(job.id)
    except Exception as exc:
        job.status = "QUEUE_FAILED"
        job.error_message = "Background queue is still unavailable; inspect Redis and worker status"
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail=job.error_message) from exc
    record_audit(db, actor=user, action="jobs.queue_retry", resource_type="job",
        resource_id=job.id, request_id=getattr(request.state, "request_id", None),
        details={"task_name": job.task_name})
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobRecord:
    job = db.get(JobRecord, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    role_keys = {role.key for role in user.roles}
    if job.created_by != user.id and "ADMIN" not in role_keys:
        raise HTTPException(status_code=403, detail="You cannot inspect this job")
    return job
