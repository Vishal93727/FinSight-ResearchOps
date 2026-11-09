"""Append-only audit event helper."""

from sqlalchemy.orm import Session

from finsight.infrastructure.database.models import AuditEvent
from finsight.identity.models import User


def record_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    request_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor.id if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            details=details or {},
        )
    )
