"""Immutable, content-addressed feature-set definitions."""
from datetime import UTC, datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from finsight.infrastructure.database.base import Base
from finsight.infrastructure.database.mixins import new_id


class FeatureSetVersion(Base):
    __tablename__ = "feature_set_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    feature_key: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    definition: Mapped[dict] = mapped_column(JSON)
    source_snapshot_id: Mapped[str] = mapped_column(ForeignKey("data_snapshots.id", ondelete="RESTRICT"), index=True)
    definition_sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (UniqueConstraint("feature_key", "version", name="uq_feature_key_version"),)
