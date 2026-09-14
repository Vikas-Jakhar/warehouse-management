import uuid
from datetime import date as date_type

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# Section 10: the system must distinguish between actual current location,
# recommended location, accepted proposed location, pending movement location,
# and rejected recommendation. The *actual* location lives here on the
# inventory record (current_location_id) and only ever changes on movement
# confirmation (Phase 6). Recommended/accepted/pending states are owned by the
# Recommendation and MovementTask models (Phase 5/6) — they reference this
# inventory record rather than mutating it, so a generated or even accepted
# recommendation can never silently change what "actual" means.
INVENTORY_STATUSES = {
    "awaiting_putaway",  # received, not yet placed in a storage location
    "in_stock",
    "reserved",
    "damaged",
    "quarantined",
}


class InventoryBatch(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "inventory_batches"

    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), index=True, nullable=False
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manufacturing_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    receiving_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    inventory_records: Mapped[list["InventoryRecord"]] = relationship(back_populates="batch")


class InventoryRecord(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "inventory_records"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), index=True, nullable=False
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    current_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("storage_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    reserved_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    damaged_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="awaiting_putaway")

    batch: Mapped["InventoryBatch | None"] = relationship(back_populates="inventory_records")

    @property
    def available_quantity(self) -> float:
        return max(0.0, self.quantity - self.reserved_quantity - self.damaged_quantity)
