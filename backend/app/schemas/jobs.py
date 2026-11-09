"""Asynchronous job request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class JobResponse(BaseModel):
    id: str
    task_name: str
    status: str
    result: dict | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
