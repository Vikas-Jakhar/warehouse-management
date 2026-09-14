import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# Statuses per section 15. "pending_review" is the landing state for every
# freshly generated recommendation (we don't distinguish a separate
# "generated" transient state - generation and pending-review happen in the
# same instant). Movement-related statuses are set by Phase 6.
RECOMMENDATION_STATUSES = {
    "pending_review",
    "accepted",
    "rejected",
    "overridden",
    "movement_created",
    "movement_in_progress",
    "movement_confirmed",
    "cancelled",
    "expired",
}

JOB_STATUSES = {"queued", "running", "succeeded", "failed"}
JOB_STAGES = {"validating", "scoring", "applying_stability_rules", "saving"}


class RecommendationJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_jobs"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    recommendations_created: Mapped[int] = mapped_column(Integer, default=0)
    inventory_records_evaluated: Mapped[int] = mapped_column(Integer, default=0)


class Recommendation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), index=True, nullable=False
    )
    inventory_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_records.id", ondelete="CASCADE"), index=True, nullable=False
    )
    current_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id", ondelete="SET NULL"), nullable=True
    )
    recommended_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id", ondelete="CASCADE"), nullable=False
    )

    reason: Mapped[list] = mapped_column(JSON, default=list)
    expected_benefit: Mapped[float] = mapped_column(Float, nullable=False)
    distance_reduction: Mapped[float | None] = mapped_column(Float, nullable=True)
    demand_classification: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_review", index=True)

    decisions: Mapped[list["RecommendationDecision"]] = relationship(
        back_populates="recommendation", cascade="all, delete-orphan"
    )


class RecommendationDecision(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_decisions"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # accept | reject | override
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    override_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    recommendation: Mapped["Recommendation"] = relationship(back_populates="decisions")
