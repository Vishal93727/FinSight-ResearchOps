"""Idempotent execution service for queued evidence-grounded research workflows."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session

from finsight.documents.models import ResearchReport
from finsight.identity.models import User
from finsight.infrastructure.database.models import JobRecord
from app.api.v1.ai_research import ask_research_question
from app.schemas.documents import ResearchAskRequest


def process_research_question_job(db: Session, job: JobRecord) -> dict:
    if job.task_name != "research.ask":
        raise ValueError("Job is not a research-question job")
    if job.status == "SUCCEEDED":
        return {"status": "already_succeeded", "job_id": job.id, **(job.result or {})}
    if job.status not in {"QUEUED", "QUEUE_FAILED", "RUNNING"}:
        return {"status": job.status.lower(), "job_id": job.id}

    user = db.get(User, job.created_by)
    if user is None:
        job.status = "FAILED"
        job.error_message = "Research job owner is unavailable"
        job.completed_at = datetime.now(UTC)
        db.commit()
        return {"status": "failed", "job_id": job.id}

    existing_report = db.get(ResearchReport, job.id)
    if existing_report is not None and existing_report.status in {
        "AWAITING_REVIEW", "APPROVED", "REJECTED", "NO_EVIDENCE"
    }:
        job.status = "SUCCEEDED"
        job.result = {"report_id": existing_report.id, "report_status": existing_report.status,
            "recovered_after_worker_redelivery": True}
        job.completed_at = datetime.now(UTC)
        db.commit()
        return {"status": "succeeded", "job_id": job.id, **job.result}

    payload = ResearchAskRequest.model_validate(job.payload or {})
    request = SimpleNamespace(state=SimpleNamespace(
        request_id=None, job_id=job.id, report_id=job.id
    ))
    report = ask_research_question(payload, request, db, user)
    job.status = "SUCCEEDED"
    job.result = {"report_id": report.id, "report_status": report.status,
        "evidence_verified": report.evidence_verified}
    job.completed_at = datetime.now(UTC)
    db.commit()
    return {"status": "succeeded", "job_id": job.id, **job.result}
