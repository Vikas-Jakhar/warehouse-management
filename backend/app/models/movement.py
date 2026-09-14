import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# Section 15/16: a movement task is the only thing that can change an
# inventory record's actual current_location_id, and only once confirmed.
MOVEMENT_STATUSES = {"pending", "in_progress", "confirmed", "cancelled"}


class MovementTask(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "movement_tasks"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    inventory_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_records.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id"), nullable=True
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    confirmation: Mapped["MovementConfirmation | None"] = relationship(
        back_populates="movement_task", cascade="all, delete-orphan", uselist=False
    )


class MovementConfirmation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "movement_confirmations"

    movement_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("movement_tasks.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    movement_task: Mapped["MovementTask"] = relationship(back_populates="confirmation")
