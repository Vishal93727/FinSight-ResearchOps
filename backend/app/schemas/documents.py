"""API contracts for research documents, evidence retrieval and human review."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.schemas.common import ORMModel


class DocumentResponse(ORMModel):
    id: str
    title: str
    filename: str
    media_type: str
    source_type: str
    source_uri: str | None
    content_sha256: str
    character_count: int
    chunk_count: int
    status: str
    document_metadata: dict
    created_at: datetime


class ResearchAskRequest(BaseModel):
    query: str = Field(min_length=8, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)
    lexical_weight: float = Field(default=0.45, ge=0, le=1)
    diversity_weight: float = Field(default=0.15, ge=0, le=0.5)
    document_ids: list[str] | None = Field(default=None, max_length=100)


class ResearchAskJobRequest(ResearchAskRequest):
    idempotency_key: str = Field(min_length=8, max_length=128)


class CitationResponse(BaseModel):
    citation_id: str
    chunk_id: str
    document_id: str
    document_title: str
    filename: str
    chunk_index: int
    text_sha256: str
    score: float
    excerpt: str


class ResearchReportResponse(ORMModel):
    id: str
    query: str
    answer: str
    status: str
    citations: list[dict]
    workflow_trace: list[dict]
    retrieval_config: dict
    evidence_verified: bool
    claim_checks: dict
    created_by: str
    reviewer_user_id: str | None
    review_comment: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ResearchReportDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    comment: str | None = Field(default=None, max_length=2000)
