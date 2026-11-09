"""Transactional hypothesis workflow rules."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from finsight.research.hypotheses.models import ResearchHypothesis


def create_hypothesis(db: Session, *, owner_user_id: str, payload: dict) -> ResearchHypothesis:
    hypothesis = ResearchHypothesis(
        title=payload["title"], symbol=payload["symbol"].upper(), thesis=payload["thesis"],
        rationale=payload.get("rationale", ""), evidence=payload.get("evidence", []),
        status="DRAFT", owner_user_id=owner_user_id,
    )
    db.add(hypothesis)
    db.flush()
    return hypothesis


def submit_for_review(db: Session, *, hypothesis_id: str) -> ResearchHypothesis | None:
    hypothesis = db.scalar(select(ResearchHypothesis).where(ResearchHypothesis.id == hypothesis_id))
    if hypothesis is None:
        return None
    if hypothesis.status != "DRAFT":
        raise ValueError("Only draft hypotheses can be submitted for review")
    hypothesis.status = "UNDER_REVIEW"
    hypothesis.version += 1
    db.flush()
    return hypothesis


def decide_hypothesis(db: Session, *, hypothesis_id: str, decision: str, note: str) -> ResearchHypothesis | None:
    hypothesis = db.scalar(select(ResearchHypothesis).where(ResearchHypothesis.id == hypothesis_id))
    if hypothesis is None:
        return None
    if hypothesis.status != "UNDER_REVIEW":
        raise ValueError("Only hypotheses submitted for review can receive a decision")
    hypothesis.status = "APPROVED" if decision == "APPROVE" else "REJECTED"
    hypothesis.decision_note = note
    hypothesis.version += 1
    db.flush()
    return hypothesis
