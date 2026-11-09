"""Versioned quantitative research hypotheses and supporting evidence."""
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class ResearchHypothesis(Base):
    __tablename__ = "research_hypotheses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(180))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    thesis: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    __table_args__ = (Index("ix_hypothesis_symbol_status", "symbol", "status"),)
