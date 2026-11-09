"""Document ingestion and evidence-retrieval endpoints."""
from __future__ import annotations
from datetime import UTC, datetime
import hashlib
from pathlib import Path, PurePath
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from finsight.core.config import get_settings
from finsight.core.security import require_roles, get_current_user
from finsight.documents.models import ResearchDocument
from finsight.identity.models import User
from finsight.infrastructure.database.session import get_db
from finsight.infrastructure.database.models import JobRecord
from app.schemas.documents import DocumentResponse
from app.schemas.jobs import JobResponse
from finsight.documents.ingestion import ingest_document_bytes, DocumentAlreadyExists
from app.services.audit import record_audit
from app.services.jobs import enqueue_document_ingestion

router = APIRouter(prefix="/documents", tags=["document intelligence"])


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_research_document(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=240),
    source_uri: str | None = Form(default=None, max_length=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER")),
):
    settings = get_settings()
    filename = PurePath((file.filename or "").replace("\\", "/")).name
    raw = await file.read(settings.max_document_upload_bytes + 1)
    if len(raw) > settings.max_document_upload_bytes:
        raise HTTPException(status_code=413, detail="Document exceeds the configured upload limit")
    try:
        doc = ingest_document_bytes(db, filename=filename, media_type=file.content_type, raw=raw,
            title=title, source_uri=source_uri, user_id=user.id, settings=settings)
    except DocumentAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record_audit(db, actor=user, action="documents.ingested", resource_type="research_document",
        resource_id=doc.id, request_id=getattr(request.state, "request_id", None),
        details={"sha256": doc.content_sha256, "chunk_count": doc.chunk_count, "filename": filename})
    db.commit(); db.refresh(doc)
    return doc


@router.post("/upload/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def queue_research_document_upload(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=240),
    source_uri: str | None = Form(default=None, max_length=1000),
    idempotency_key: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER")),
):
    settings = get_settings()
    filename = PurePath((file.filename or "").replace("\\", "/")).name
    raw = await file.read(settings.max_document_upload_bytes + 1)
    if not filename or len(filename) > 255:
        raise HTTPException(status_code=422, detail="A valid filename is required")
    if len(raw) > settings.max_document_upload_bytes:
        raise HTTPException(status_code=413, detail="Document exceeds the configured upload limit")
    if source_uri is not None and not source_uri.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="source_uri must use HTTP or HTTPS")
    if idempotency_key is not None and not 8 <= len(idempotency_key) <= 128:
        raise HTTPException(status_code=422, detail="idempotency_key must contain 8-128 characters")
    digest = hashlib.sha256(raw).hexdigest()
    if idempotency_key:
        existing = db.scalar(select(JobRecord).where(JobRecord.created_by == user.id,
            JobRecord.idempotency_key == idempotency_key))
        if existing is not None:
            if existing.task_name != "documents.ingest" or (existing.payload or {}).get("content_sha256") != digest:
                raise HTTPException(status_code=409, detail="This idempotency key was already used for a different job or document")
            return existing
    if db.scalar(select(ResearchDocument).where(ResearchDocument.content_sha256 == digest)) is not None:
        raise HTTPException(status_code=409, detail="This exact document is already ingested")
    staging = Path(settings.data_storage_path).resolve() / "incoming_documents"
    staging.mkdir(parents=True, exist_ok=True)
    staged_path = staging / f"{digest}.upload"
    temporary = staged_path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    temporary.replace(staged_path)
    job = JobRecord(task_name="documents.ingest", status="QUEUED",
        payload={"filename": filename, "media_type": (file.content_type or "application/octet-stream")[:120],
            "title": title, "source_uri": source_uri, "staged_path": str(staged_path),
            "content_sha256": digest, "byte_count": len(raw)},
        idempotency_key=idempotency_key, created_by=user.id)
    db.add(job); db.flush()
    record_audit(db, actor=user, action="documents.ingestion_queued", resource_type="job",
        resource_id=job.id, request_id=getattr(request.state, "request_id", None),
        details={"sha256": digest, "filename": filename})
    db.commit(); db.refresh(job)
    try:
        enqueue_document_ingestion(job.id)
    except Exception as exc:
        job.status = "QUEUE_FAILED"
        job.error_message = "Document worker queue is unavailable; retry after checking Redis and worker status"
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail=job.error_message) from exc
    return job


@router.get("", response_model=list[DocumentResponse])
def list_research_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(ResearchDocument).order_by(ResearchDocument.created_at.desc()).limit(200)).all())


@router.get("/{document_id}", response_model=DocumentResponse)
def get_research_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = db.get(ResearchDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
