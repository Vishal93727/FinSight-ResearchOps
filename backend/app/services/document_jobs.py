"""Idempotent processing service for staged document-ingestion jobs."""
from __future__ import annotations

import hashlib
from pathlib import Path
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from finsight.core.config import get_settings
from finsight.documents.ingestion import ingest_document_bytes
from finsight.identity.models import User
from finsight.infrastructure.database.models import JobRecord
from finsight.documents.models import ResearchDocument
from sqlalchemy import select
from app.services.audit import record_audit


def process_document_ingestion_job(db: Session, job: JobRecord) -> dict:
    if job.task_name != "documents.ingest":
        raise ValueError("Job is not a document-ingestion job")
    if job.status == "SUCCEEDED":
        return {"status": "already_succeeded", **(job.result or {})}
    if job.status not in {"QUEUED", "QUEUE_FAILED", "RUNNING"}:
        return {"status": job.status.lower(), "job_id": job.id}
    payload = job.payload or {}
    settings = get_settings()
    staging_root = (Path(settings.data_storage_path).resolve() / "incoming_documents").resolve()
    staged_path = Path(str(payload.get("staged_path", ""))).resolve()
    if staged_path.parent != staging_root or not staged_path.is_file():
        raise ValueError("Staged document path is missing or outside the permitted upload directory")
    raw = staged_path.read_bytes()
    if len(raw) != int(payload.get("byte_count", -1)):
        raise ValueError("Staged document byte count does not match the upload manifest")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != payload.get("content_sha256"):
        raise ValueError("Staged document hash does not match the upload manifest")
    user = db.get(User, job.created_by)
    if user is None:
        raise ValueError("Document job owner no longer exists")
    existing = db.scalar(select(ResearchDocument).where(ResearchDocument.content_sha256 == digest))
    if existing is not None:
        job.result = {"document_id": existing.id, "content_sha256": digest,
                      "chunk_count": existing.chunk_count, "document_status": existing.status, "deduplicated": True}
        job.status = "SUCCEEDED"
        job.completed_at = datetime.now(UTC)
        db.commit()
        staged_path.unlink(missing_ok=True)
        return {"status": "succeeded", "job_id": job.id, **job.result}
    document = ingest_document_bytes(db, filename=str(payload["filename"]),
        media_type=str(payload.get("media_type") or "application/octet-stream"), raw=raw,
        title=payload.get("title"), source_uri=payload.get("source_uri"),
        user_id=user.id, settings=settings)
    record_audit(db, actor=user, action="documents.ingested_from_job", resource_type="research_document",
        resource_id=document.id, request_id=None,
        details={"sha256": digest, "chunk_count": document.chunk_count, "job_id": job.id})
    job.result = {"document_id": document.id, "content_sha256": digest,
                  "chunk_count": document.chunk_count, "document_status": "READY"}
    job.status = "SUCCEEDED"
    job.completed_at = datetime.now(UTC)
    db.commit()
    staged_path.unlink(missing_ok=True)
    return {"status": "succeeded", "job_id": job.id, **job.result}
