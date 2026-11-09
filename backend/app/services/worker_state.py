"""Transactional worker-state helpers shared by Celery task implementations."""
from __future__ import annotations

from datetime import UTC, datetime


def mark_failed_after_rollback(db, model, record_id: str, error_message: str) -> None:
    """Discard partial domain writes before persisting a worker failure state.

    A worker may have added or changed domain entities before an exception is raised.
    Committing a FAILED status without rolling back first could accidentally commit
    those incomplete writes. Reload the job/run after rollback, then commit only the
    failure marker in a clean transaction.
    """
    db.rollback()
    record = db.get(model, record_id)
    if record is None or record.status == "SUCCEEDED":
        return
    record.status = "FAILED"
    record.error_message = error_message
    record.completed_at = datetime.now(UTC)
    db.commit()
