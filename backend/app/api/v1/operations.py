"""Read-only operational overview for service, worker and portfolio health."""
from datetime import UTC, datetime, timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import Session
from finsight.core.config import get_settings
from finsight.core.security import require_roles
from finsight.experiments.models import ExperimentRun
from finsight.execution.models import PaperAccount, PaperOrder
from finsight.feedback.models import PredictionOutcome, DriftAssessment, ResearchSuggestion
from finsight.governance.models import ModelVersion
from finsight.identity.models import User
from app.schemas.phase5 import StaleJobRecoveryRequest
from app.services.audit import record_audit
from finsight.infrastructure.database.models import JobRecord
from finsight.infrastructure.database.session import get_db

router = APIRouter(prefix="/operations", tags=["operations and administration"])
_ALLOWED = ("ADMIN", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER")


def _group_counts(db: Session, model, column) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).select_from(model).group_by(column)).all()
    return {str(key or "UNKNOWN"): int(count) for key, count in rows}


@router.get("/summary")
def operations_summary(db: Session = Depends(get_db), user: User = Depends(require_roles(*_ALLOWED))):
    settings = get_settings()
    jobs = _group_counts(db, JobRecord, JobRecord.status)
    runs = _group_counts(db, ExperimentRun, ExperimentRun.status)
    orders = _group_counts(db, PaperOrder, PaperOrder.status)
    account_count = db.scalar(select(func.count()).select_from(PaperAccount)) or 0
    kill_switches = db.scalar(select(func.count()).select_from(PaperAccount).where(PaperAccount.kill_switch.is_(True))) or 0
    outcome_count = db.scalar(select(func.count()).select_from(PredictionOutcome)) or 0
    drift_open = db.scalar(select(func.count()).select_from(DriftAssessment).where(DriftAssessment.overall_status == "DRIFT")) or 0
    suggestions_open = db.scalar(select(func.count()).select_from(ResearchSuggestion).where(ResearchSuggestion.status == "PROPOSED")) or 0
    model_states = _group_counts(db, ModelVersion, ModelVersion.state)
    redis_state = "unavailable"
    try:
        import redis
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        redis_state = "ready" if client.ping() else "unavailable"
    except Exception:
        redis_state = "unavailable"

    # Redis availability is not the same as worker availability. Ask Celery for a
    # bounded remote-control ping and report it separately for operations.
    worker_state = "unavailable"
    worker_names: list[str] = []
    try:
        from app.workers.celery_app import celery_app
        responses = celery_app.control.inspect(timeout=1.0).ping() or {}
        worker_names = sorted(responses.keys())
        worker_state = "ready" if worker_names else "unavailable"
    except Exception:
        worker_state = "unavailable"

    stale_cutoff = datetime.now(UTC) - timedelta(minutes=30)
    stale_jobs = db.scalar(select(func.count()).select_from(JobRecord).where(
        or_(
            and_(JobRecord.status.in_(["QUEUED", "QUEUE_FAILED"]), JobRecord.created_at <= stale_cutoff),
            and_(JobRecord.status == "RUNNING", JobRecord.started_at.is_not(None), JobRecord.started_at <= stale_cutoff),
        )
    )) or 0
    failed_rows = list(db.scalars(select(JobRecord).where(
        JobRecord.status.in_(["FAILED", "QUEUE_FAILED"])
    ).order_by(JobRecord.completed_at.desc().nullslast(), JobRecord.created_at.desc()).limit(8)).all())
    recent_failures = [{
        "id": row.id, "task_name": row.task_name, "status": row.status,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        # Do not send exception messages to broad read-only operations roles.
        "failure_recorded": bool(row.error_message),
    } for row in failed_rows]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": settings.app_env,
        "services": {"api": "ready", "database": "ready", "redis": redis_state,
                     "worker": worker_state},
        "worker_names": worker_names,
        "stale_job_count": int(stale_jobs),
        "recent_failures": recent_failures,
        "jobs": jobs,
        "experiment_runs": runs,
        "paper_execution": {"accounts": int(account_count), "kill_switch_enabled_accounts": int(kill_switches), "orders_by_status": orders},
        "governance": {"model_versions_by_state": model_states},
        "feedback": {"realised_outcomes": int(outcome_count), "open_drift_assessments": int(drift_open), "proposed_research_suggestions": int(suggestions_open)},
        "notes": ["Paper execution only; no live broker is configured.", "Redis status is unavailable when its optional client or service is not installed.", "Counts are current database snapshots, not a service-level objective or uptime guarantee."],
    }


@router.post("/recover-stale-jobs")
def recover_stale_jobs(payload: StaleJobRecoveryRequest, request: Request,
                       db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))):
    """Preview stale jobs by default; requeue only after explicit administrator confirmation."""
    cutoff = datetime.now(UTC) - timedelta(minutes=payload.stale_after_minutes)
    stale_filter = or_(
        and_(JobRecord.status.in_(["QUEUED", "QUEUE_FAILED"]), JobRecord.created_at <= cutoff),
        and_(JobRecord.status == "RUNNING", JobRecord.started_at.is_not(None), JobRecord.started_at <= cutoff),
    )
    jobs = list(db.scalars(select(JobRecord).where(stale_filter)
        .order_by(JobRecord.created_at.asc()).limit(payload.limit)).all())
    preview = [{"id": job.id, "task_name": job.task_name, "status": job.status,
                "created_at": job.created_at.isoformat(), "started_at": job.started_at.isoformat() if job.started_at else None}
               for job in jobs]
    if not payload.confirm_requeue:
        return {"mode": "DRY_RUN", "candidate_count": len(preview), "candidates": preview,
                "warning": "Inspect worker health and logs before confirming requeue."}

    from app.services.jobs import (enqueue_system_ping, enqueue_document_ingestion,
        enqueue_model_evaluation, enqueue_research_ask, enqueue_rl_evaluation)
    dispatchers = {"system.ping": enqueue_system_ping, "documents.ingest": enqueue_document_ingestion,
        "ml.evaluate": enqueue_model_evaluation, "research.ask": enqueue_research_ask,
        "rl.evaluate": enqueue_rl_evaluation}
    results = []
    for job in jobs:
        dispatch = dispatchers.get(job.task_name)
        if dispatch is None:
            results.append({"job_id": job.id, "status": "UNSUPPORTED_TASK", "task_name": job.task_name})
            continue
        job.status = "QUEUED"; job.started_at = None; job.completed_at = None; job.error_message = None
        db.commit()
        try:
            dispatch(job.id)
            results.append({"job_id": job.id, "status": "REQUEUED"})
        except Exception as exc:
            job.status = "QUEUE_FAILED"; job.error_message = type(exc).__name_; job.completed_at = datetime.now(UTC)
            db.commit()
            results.append({"job_id": job.id, "status": "QUEUE_FAILED"})
    record_audit(db, actor=user, action="operations.stale_jobs_recovered", resource_type="job_recovery_batch",
        request_id=getattr(request.state, "request_id", None), details={"candidate_count": len(preview), "results": results})
    db.commit()
    return {"mode": "REQUEUE_CONFIRMED", "candidate_count": len(preview), "results": results,
            "warning": "Requeued tasks are idempotency-protected where supported; verify job result and audit history."}
