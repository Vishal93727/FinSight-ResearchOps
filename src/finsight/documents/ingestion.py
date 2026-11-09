"""Reusable bounded document ingestion for synchronous API and Celery worker paths."""
from __future__ import annotations

import hashlib
from pathlib import PurePath
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from finsight.documents.models import ResearchDocument, DocumentChunk
from finsight.documents.parsers import parse_document
from finsight.documents.chunking import chunk_text
from finsight.documents.embeddings import get_embedding_provider
from finsight.documents.vector_store import pgvector_literal


class DocumentAlreadyExists(ValueError):
    """Raised when the exact source bytes have already been ingested."""


def ingest_document_bytes(db: Session, *, filename: str, media_type: str | None, raw: bytes,
                           title: str | None, source_uri: str | None, user_id: str,
                           settings) -> ResearchDocument:
    if not raw:
        raise ValueError("Document upload is empty")
    if len(raw) > settings.max_document_upload_bytes:
        raise ValueError("Document exceeds the configured upload limit")
    safe_filename = PurePath((filename or "").replace("\\", "/")).name
    if not safe_filename or len(safe_filename) > 255:
        raise ValueError("A valid filename is required")
    if source_uri is not None and not source_uri.startswith(("https://", "http://")):
        raise ValueError("source_uri must use HTTP or HTTPS")
    content, parser_metadata = parse_document(safe_filename, media_type, raw)
    chunks = chunk_text(content, settings.document_chunk_size, settings.document_chunk_overlap)
    if not chunks:
        raise ValueError("No chunks could be created from this document")
    if len(chunks) > settings.max_document_chunks:
        raise ValueError("Document creates too many chunks; split the source document")
    provider = get_embedding_provider(settings.document_embedding_provider,
        settings.document_embedding_dimensions, settings.document_embedding_model)
    digest = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(select(ResearchDocument).where(ResearchDocument.content_sha256 == digest))
    if existing is not None:
        raise DocumentAlreadyExists(f"This exact document is already ingested (document_id={existing.id})")
    use_pgvector = getattr(settings, "document_vector_backend", "json") == "pgvector"
    if use_pgvector and db.get_bind().dialect.name != "postgresql":
        raise RuntimeError("pgvector storage is only available on PostgreSQL")
    if use_pgvector and provider.dimensions != 384:
        raise ValueError("The active pgvector index requires 384-dimensional embeddings")
    document = ResearchDocument(
        title=((title or safe_filename).strip() or safe_filename)[:240], filename=safe_filename,
        media_type=(media_type or "application/octet-stream")[:120], source_type="UPLOAD",
        source_uri=source_uri, content_sha256=digest, content_text=content,
        character_count=len(content), chunk_count=len(chunks), status="READY",
        document_metadata=parser_metadata | {"chunk_size": settings.document_chunk_size,
            "chunk_overlap": settings.document_chunk_overlap, "embedding_provider": provider.name,
            "embedding_model": provider.model_name, "embedding_dimensions": provider.dimensions,
            "vector_backend": "pgvector" if use_pgvector else "json", "original_bytes": len(raw)},
        created_by=user_id,
    )
    db.add(document)
    db.flush()
    for chunk in chunks:
        vector = provider.embed(chunk.text)
        record = DocumentChunk(document_id=document.id, chunk_index=chunk.index, text=chunk.text,
            text_sha256=hashlib.sha256(chunk.text.encode()).hexdigest(), embedding=vector,
            token_count=chunk.token_count, metadata_json={"section": chunk.section} if chunk.section else {})
        db.add(record)
        if use_pgvector:
            db.flush()
            db.execute(text("UPDATE document_chunks SET embedding_vector = CAST(:vector AS vector) WHERE id = :chunk_id"),
                {"vector": pgvector_literal(vector, 384), "chunk_id": record.id})
    db.flush()
    return document
