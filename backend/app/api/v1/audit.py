"""Restricted audit event inspection endpoint."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight.core.security import require_roles
from finsight.infrastructure.database.session import get_db
from finsight.infrastructure.database.models import AuditEvent
from finsight.identity.models import User

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    actor_user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    request_id: str | None
    details: dict
    created_at: datetime


@router.get("/events", response_model=list[AuditEventResponse])
def list_audit_events(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "RISK_REVIEWER")),
) -> list[AuditEvent]:
    safe_limit = max(1, min(limit, 200))
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(safe_limit)).all())
