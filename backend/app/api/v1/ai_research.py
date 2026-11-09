"""Evidence-grounded research Q&A with mandatory human review."""
from datetime import UTC, datetime
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy import select
from sqlalchemy.orm import Session
from finsight.core.config import get_settings
from finsight.core.security import get_current_user, require_roles
from finsight.documents.models import ResearchDocument, DocumentChunk, ResearchReport, ResearchWorkflowCheckpoint
from finsight.documents.retrieval import (
    RetrievalCandidate, RetrievedEvidence, hybrid_retrieve, get_reranker,
)
from finsight.documents.embeddings import get_embedding_provider
from finsight.documents.vector_store import pgvector_literal
from finsight.identity.models import User
from finsight.infrastructure.database.session import get_db
from finsight.infrastructure.database.mixins import new_id
from finsight.infrastructure.database.models import JobRecord
from finsight.research.graphs.workflow import (
    build_evidence_report, resume_evidence_report, get_research_synthesizer, ExtractiveSynthesizer,
)
from app.schemas.documents import (
    ResearchAskRequest, ResearchAskJobRequest, ResearchReportResponse, ResearchReportDecision,
)
from app.schemas.jobs import JobResponse
from app.services.audit import record_audit
from app.services.jobs import enqueue_research_ask

router = APIRouter(prefix="/research", tags=["AI-assisted research"])


@router.post("/ask", response_model=ResearchReportResponse, status_code=201)
def ask_research_question(payload: ResearchAskRequest, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER"))):
    settings = get_settings()
    try:
        embedding_provider = get_embedding_provider(settings.document_embedding_provider,
            settings.document_embedding_dimensions, settings.document_embedding_model)
        reranker = get_reranker(settings.document_reranker, settings.document_reranker_model)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    candidates = []
    incompatible_documents = set()
    if settings.document_vector_backend == "pgvector":
        if db.get_bind().dialect.name != "postgresql":
            raise HTTPException(status_code=503, detail="pgvector retrieval requires PostgreSQL")
        if embedding_provider.dimensions != 384:
            raise HTTPException(status_code=422, detail="The active pgvector index requires 384-dimensional embeddings")
        query_vector = embedding_provider.embed(payload.query)
        scope = "d.status = 'READY'"
        scope_params = {}
        if payload.document_ids:
            scope += " AND d.id = ANY(:document_ids)"
            scope_params["document_ids"] = payload.document_ids
        # Refuse incomplete or mixed vector indexes instead of silently searching
        # only a subset of the user's READY documents.
        try:
            ready_metadata = db.execute(text(f"""
                SELECT d.id, d.document_metadata FROM research_documents d WHERE {scope}
            """), scope_params).mappings().all()
            incompatible = [row["id"] for row in ready_metadata
                if (row["document_metadata"] or {}).get("embedding_provider") != embedding_provider.name
                or (row["document_metadata"] or {}).get("embedding_model") != embedding_provider.model_name]
            if incompatible:
                raise HTTPException(status_code=409, detail=(
                    f"{len(incompatible)} READY documents use a different embedding provider/model; "
                    "re-ingest them or restrict document_ids before pgvector retrieval"))
            missing_vectors = db.execute(text(f"""
                SELECT COUNT(*) FROM document_chunks c
                JOIN research_documents d ON d.id = c.document_id
                WHERE {scope} AND c.embedding_vector IS NULL
            """), scope_params).scalar_one()
            if missing_vectors:
                raise HTTPException(status_code=409, detail=(
                    f"{missing_vectors} READY chunks are missing pgvector values; run "
                    "scripts/backfill_pgvector_embeddings.py after applying migrations"))
            filters = " AND d.status = 'READY' AND c.embedding_vector IS NOT NULL"
            params = {"query_vector": pgvector_literal(query_vector, 384),
                      "candidate_limit": min(4000, max(400, payload.top_k * 40))}
            if payload.document_ids:
                filters += " AND d.id = ANY(:document_ids)"
                params["document_ids"] = payload.document_ids
            rows = db.execute(text(f"""
                SELECT c.id AS chunk_id, c.document_id, c.chunk_index, c.text, c.text_sha256, c.embedding,
                       d.title AS document_title, d.filename, d.document_metadata
                FROM document_chunks c JOIN research_documents d ON d.id = c.document_id
                WHERE {filters}
                ORDER BY c.embedding_vector <=> CAST(:query_vector AS vector)
                LIMIT :candidate_limit
            """), params).mappings().all()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=(
                "pgvector schema/index is unavailable; apply Alembic migrations and verify the vector extension")) from exc
        for row in rows:
            metadata = row["document_metadata"] or {}
            if metadata.get("embedding_provider") != embedding_provider.name or metadata.get("embedding_model") != embedding_provider.model_name:
                incompatible_documents.add(row["document_id"])
                continue
            candidates.append(RetrievalCandidate(chunk_id=row["chunk_id"], document_id=row["document_id"],
                document_title=row["document_title"], filename=row["filename"], chunk_index=row["chunk_index"],
                text=row["text"], text_sha256=row["text_sha256"], embedding=row["embedding"]))
    else:
        query = db.query(DocumentChunk, ResearchDocument).join(
            ResearchDocument, ResearchDocument.id == DocumentChunk.document_id
        ).filter(ResearchDocument.status == "READY").order_by(DocumentChunk.document_id, DocumentChunk.chunk_index).limit(25_000)
        if payload.document_ids:
            query = query.filter(ResearchDocument.id.in_(payload.document_ids))
        for chunk, doc in query.all():
            metadata = doc.document_metadata or {}
            if metadata.get("embedding_provider") != embedding_provider.name or metadata.get("embedding_model") != embedding_provider.model_name:
                incompatible_documents.add(doc.id)
                continue
            candidates.append(RetrievalCandidate(chunk_id=chunk.id, document_id=doc.id, document_title=doc.title,
                filename=doc.filename, chunk_index=chunk.chunk_index, text=chunk.text,
                text_sha256=chunk.text_sha256, embedding=chunk.embedding))
    if not candidates and incompatible_documents:
        raise HTTPException(status_code=409, detail="No documents use the active embedding model; re-ingest documents after changing embedding settings")
    try:
        evidence = hybrid_retrieve(payload.query, candidates, payload.top_k, payload.lexical_weight,
            payload.diversity_weight, embedding_provider=embedding_provider, reranker=reranker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    requested_report_id = getattr(request.state, "report_id", None)
    report_id = requested_report_id or new_id()
    report = db.get(ResearchReport, report_id) if requested_report_id else None
    if report is not None and report.created_by != user.id:
        raise HTTPException(status_code=409, detail="Research workflow identifier is already in use")
    if report is not None and report.status in {"AWAITING_REVIEW", "APPROVED", "REJECTED", "NO_EVIDENCE"}:
        return report
    retrieval_config = {"top_k": payload.top_k, "lexical_weight": payload.lexical_weight,
        "diversity_weight": payload.diversity_weight,
        "embedding_provider": embedding_provider.name, "embedding_model": embedding_provider.model_name,
        "vector_backend": settings.document_vector_backend, "reranker": settings.document_reranker,
        "reranker_model": settings.document_reranker_model if settings.document_reranker != "none" else None,
        "workflow_engine": settings.research_workflow_engine,
        "queued_job_id": getattr(request.state, "job_id", None),
        "synthesis_provider": settings.research_synthesis_provider if evidence else "extractive",
        "synthesis_model": settings.research_llm_model if evidence and settings.research_synthesis_provider != "extractive" else None}
    if report is None:
        report = ResearchReport(id=report_id, query=payload.query, answer="", status="PROCESSING",
            citations=[], workflow_trace=[], retrieval_config=retrieval_config, evidence_verified=False,
            claim_checks={}, created_by=user.id)
        db.add(report)
    else:
        # A redelivered Celery task may find an interrupted PROCESSING record.
        # Clear old node snapshots and deterministically rebuild this same report.
        db.query(ResearchWorkflowCheckpoint).filter(
            ResearchWorkflowCheckpoint.workflow_id == report_id
        ).delete(synchronize_session=False)
        report.query = payload.query
        report.answer = ""
        report.status = "PROCESSING"
        report.citations = []
        report.workflow_trace = []
        report.retrieval_config = retrieval_config
        report.evidence_verified = False
        report.claim_checks = {}
        report.review_comment = None
    report.retrieval_config = retrieval_config
    db.commit()
    try:
        synthesizer = (get_research_synthesizer(settings.research_synthesis_provider, settings.research_llm_model)
            if evidence else ExtractiveSynthesizer())
        def persist_checkpoint(snapshot: dict) -> None:
            db.add(ResearchWorkflowCheckpoint(workflow_id=report_id, sequence=snapshot["sequence"],
                node=snapshot["node"], status=snapshot["status"], state_snapshot=snapshot["state"]))
            db.commit()
        workflow = build_evidence_report(payload.query, evidence, synthesizer=synthesizer,
            workflow_engine=settings.research_workflow_engine, checkpoint_callback=persist_checkpoint)
    except RuntimeError as exc:
        report.status = "FAILED"
        report.review_comment = "Research workflow execution failed; inspect service logs and retry."
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        report.status = "FAILED"
        report.review_comment = "Research workflow execution failed unexpectedly."
        db.commit()
        raise
    report.answer = workflow["answer"]
    report.status = workflow["status"]
    report.citations = workflow["citations"]
    report.workflow_trace = workflow["workflow_trace"]
    report.evidence_verified = workflow["evidence_verified"]
    report.claim_checks = workflow.get("claim_checks", {})
    db.flush()
    record_audit(db, actor=user, action="research.evidence_report_generated", resource_type="research_report",
        resource_id=report.id, request_id=getattr(request.state, "request_id", None),
        details={"evidence_count": len(evidence), "evidence_verified": workflow["evidence_verified"],
                 "claim_check_passed": bool(workflow.get("claim_checks", {}).get("passed"))})
    db.commit(); db.refresh(report)
    return report


@router.post("/ask/jobs", response_model=JobResponse, status_code=202)
def queue_research_question(payload: ResearchAskJobRequest, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER"))):
    """Queue a bounded RAG workflow; the worker writes the report and node checkpoints."""
    request_payload = payload.model_dump(exclude={"idempotency_key"})
    existing = db.scalar(select(JobRecord).where(
        JobRecord.created_by == user.id, JobRecord.idempotency_key == payload.idempotency_key
    ))
    if existing is not None:
        if existing.task_name != "research.ask" or existing.payload != request_payload:
            raise HTTPException(status_code=409, detail="This idempotency key was already used for a different operation")
        return existing
    job = JobRecord(task_name="research.ask", status="QUEUED", payload=request_payload,
        idempotency_key=payload.idempotency_key, created_by=user.id)
    db.add(job)
    db.flush()
    record_audit(db, actor=user, action="research.question_queued", resource_type="job",
        resource_id=job.id, request_id=getattr(request.state, "request_id", None),
        details={"query_sha256": __import__("hashlib").sha256(payload.query.encode()).hexdigest()})
    db.commit()
    db.refresh(job)
    try:
        enqueue_research_ask(job.id)
    except Exception as exc:
        job.status = "QUEUE_FAILED"
        job.error_message = "Research worker queue is unavailable; retry after checking Redis and worker status"
        job.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail=job.error_message) from exc
    return job


@router.post("/reports/{report_id}/resume", response_model=ResearchReportResponse)
def resume_failed_research_report(report_id: str, request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER"))):
    """Resume a failed report from its last durable workflow-node checkpoint."""
    report = db.get(ResearchReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Research report not found")
    if report.created_by != user.id and "ADMIN" not in {role.key for role in user.roles}:
        raise HTTPException(status_code=403, detail="You cannot resume another researcher's report")
    if report.status != "FAILED":
        raise HTTPException(status_code=409, detail="Only failed research reports can be resumed")
    checkpoint = db.scalar(select(ResearchWorkflowCheckpoint).where(
        ResearchWorkflowCheckpoint.workflow_id == report_id
    ).order_by(ResearchWorkflowCheckpoint.sequence.desc()).limit(1))
    if checkpoint is None or checkpoint.node not in {"validate_query", "retrieve_evidence", "synthesize", "verify_citations", "human_review"}:
        raise HTTPException(status_code=409, detail="No resumable workflow checkpoint is available")
    snapshot = checkpoint.state_snapshot or {}
    if snapshot.get("query") != report.query:
        raise HTTPException(status_code=409, detail="Checkpoint query does not match the report")
    if checkpoint.node in {"synthesize", "verify_citations", "human_review"}:
        saved_answer = str(snapshot.get("answer", ""))
        saved_hash = snapshot.get("answer_sha256")
        if len(saved_answer) > 20_000 or not saved_hash or hashlib.sha256(saved_answer.encode()).hexdigest() != saved_hash:
            raise HTTPException(status_code=409, detail="Checkpoint answer is missing or failed its integrity check")
    evidence_ids = list(dict.fromkeys(snapshot.get("evidence_ids", [])))
    if len(evidence_ids) > 20:
        raise HTTPException(status_code=409, detail="Checkpoint evidence count exceeds the safe resume limit")
    evidence: list[RetrievedEvidence] = []
    citation_by_chunk = {item.get("chunk_id"): item for item in snapshot.get("citations", [])
                         if isinstance(item, dict) and item.get("chunk_id")}
    if evidence_ids:
        rows = db.query(DocumentChunk, ResearchDocument).join(
            ResearchDocument, ResearchDocument.id == DocumentChunk.document_id
        ).filter(DocumentChunk.id.in_(evidence_ids)).all()
        by_id = {chunk.id: (chunk, document) for chunk, document in rows}
        if set(by_id) != set(evidence_ids):
            raise HTTPException(status_code=409, detail="One or more checkpoint evidence chunks are no longer available")
        for index, chunk_id in enumerate(evidence_ids, start=1):
            chunk, document = by_id[chunk_id]
            if document.status != "READY":
                raise HTTPException(status_code=409, detail="Checkpoint source document is no longer READY")
            citation = citation_by_chunk.get(chunk_id, {})
            if citation.get("text_sha256") and citation["text_sha256"] != chunk.text_sha256:
                raise HTTPException(status_code=409, detail="Checkpoint source hash has changed")
            evidence.append(RetrievedEvidence(
                citation_id=str(citation.get("citation_id") or f"E{index}"),
                chunk_id=chunk.id, document_id=document.id, title=document.title,
                filename=document.filename, chunk_index=chunk.chunk_index, text=chunk.text,
                text_sha256=chunk.text_sha256,
                lexical_score=float(citation.get("score", 0.0)), vector_score=0.0,
                combined_score=float(citation.get("score", 0.0)), embedding=chunk.embedding,
                rerank_score=citation.get("rerank_score")))
    settings = get_settings()
    retrieval_config = report.retrieval_config or {}
    synthesizer = ExtractiveSynthesizer()
    if checkpoint.node in {"validate_query", "retrieve_evidence"}:
        try:
            synthesizer = get_research_synthesizer(
                retrieval_config.get("synthesis_provider", "extractive"),
                retrieval_config.get("synthesis_model") or settings.research_llm_model)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    report.status = "PROCESSING"
    report.review_comment = None
    db.commit()
    def persist_checkpoint(snapshot_update: dict) -> None:
        db.add(ResearchWorkflowCheckpoint(workflow_id=report_id,
            sequence=snapshot_update["sequence"], node=snapshot_update["node"],
            status=snapshot_update["status"], state_snapshot=snapshot_update["state"]))
        db.commit()
    try:
        workflow = resume_evidence_report(report.query, evidence, snapshot, checkpoint.node,
            checkpoint.sequence, synthesizer=synthesizer, checkpoint_callback=persist_checkpoint)
    except Exception as exc:
        db.rollback()
        report = db.get(ResearchReport, report_id)
        if report is not None:
            report.status = "FAILED"
            report.review_comment = "Research workflow resume failed; inspect service logs and retry."
            db.commit()
        raise HTTPException(status_code=503, detail="Research workflow could not resume from its saved checkpoint") from exc
    report = db.get(ResearchReport, report_id)
    report.answer = workflow["answer"]
    report.status = workflow["status"]
    report.citations = workflow["citations"]
    report.workflow_trace = workflow["workflow_trace"]
    report.evidence_verified = workflow["evidence_verified"]
    report.claim_checks = workflow.get("claim_checks", {})
    record_audit(db, actor=user, action="research.workflow_resumed", resource_type="research_report",
        resource_id=report.id, request_id=getattr(request.state, "request_id", None),
        details={"checkpoint_node": checkpoint.node, "checkpoint_sequence": checkpoint.sequence,
                 "evidence_count": len(evidence), "evidence_verified": report.evidence_verified})
    db.commit()
    db.refresh(report)
    return report


@router.get("/reports", response_model=list[ResearchReportResponse])
def list_research_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(ResearchReport).order_by(ResearchReport.created_at.desc()).limit(200)).all())


@router.get("/reports/{report_id}", response_model=ResearchReportResponse)
def get_research_report(report_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = db.get(ResearchReport, report_id)
    if report is None: raise HTTPException(status_code=404, detail="Research report not found")
    return report


@router.get("/reports/{report_id}/checkpoints")
def list_research_workflow_checkpoints(report_id: str, db: Session = Depends(get_db),
                                      user: User = Depends(get_current_user)):
    report = db.get(ResearchReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Research report not found")
    checkpoints = db.scalars(select(ResearchWorkflowCheckpoint).where(
        ResearchWorkflowCheckpoint.workflow_id == report_id
    ).order_by(ResearchWorkflowCheckpoint.sequence.asc())).all()
    return [{"sequence": item.sequence, "node": item.node, "status": item.status,
             "state_snapshot": item.state_snapshot, "created_at": item.created_at.isoformat()} for item in checkpoints]


@router.post("/reports/{report_id}/decision", response_model=ResearchReportResponse)
def decide_research_report(report_id: str, payload: ResearchReportDecision, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "RISK_REVIEWER"))):
    report = db.get(ResearchReport, report_id)
    if report is None: raise HTTPException(status_code=404, detail="Research report not found")
    if report.status != "AWAITING_REVIEW" or not report.evidence_verified:
        raise HTTPException(status_code=409, detail="Only citation-verified reports awaiting review can be decided")
    if report.created_by == user.id and "ADMIN" not in {role.key for role in user.roles}:
        raise HTTPException(status_code=403, detail="The report author cannot approve their own report")
    report.status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    report.reviewer_user_id = user.id; report.review_comment = payload.comment
    report.reviewed_at = datetime.now(UTC)
    report.workflow_trace = list(report.workflow_trace) + [{"node": "human_review", "status": report.status,
        "reviewer_user_id": user.id, "reviewed_at": report.reviewed_at.isoformat()}]
    record_audit(db, actor=user, action=f"research.report_{'approved' if payload.decision == 'APPROVE' else 'rejected'}",
        resource_type="research_report", resource_id=report.id,
        request_id=getattr(request.state, "request_id", None), details={"decision": payload.decision})
    db.commit(); db.refresh(report)
    return report
