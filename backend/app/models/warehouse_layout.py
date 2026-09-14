import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# Zone-level classification. A zone is an area of the warehouse; individual
# storage_locations sit inside a zone (nullable for point-type locations that
# are not part of a bulk storage zone, e.g. a single receiving dock).
ZONE_TYPES = {
    "receiving",
    "inbound",
    "staging",
    "putaway",
    "storage",
    "picking",
    "packing",
    "dispatch",
    "loading",
    "returns",
    "damaged",
    "cold_storage",
    "restricted",
    "non_storage",
}

# location_type distinguishes what role a specific point/bin plays. This is
# what layout validation checks for "missing receiving point" / "missing
# dispatch point" rules, independent of which zone it happens to sit in.
LOCATION_TYPES = {
    "storage",
    "receiving",
    "dispatch",
    "staging",
    "putaway",
    "picking",
    "packing",
    "loading",
    "returns",
    "damaged",
    "cold_storage",
    "restricted",
    "entrance",
    "aisle",
}

STORAGE_TYPES = {"shelf", "rack", "bin", "pallet", "floor", "bulk", "cold_unit"}


class Zone(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "zones"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_code: Mapped[str] = mapped_column(String(50), nullable=False)
    zone_type: Mapped[str] = mapped_column(String(50), nullable=False)
    temperature_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    hazard_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    locations: Mapped[list["StorageLocation"]] = relationship(back_populates="zone")

    __table_args__ = (UniqueConstraint("warehouse_id", "zone_code", name="uq_zone_warehouse_code"),)


class StorageLocation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "storage_locations"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True, index=True
    )

    location_code: Mapped[str] = mapped_column(String(100), nullable=False)
    location_type: Mapped[str] = mapped_column(String(50), nullable=False, default="storage")

    aisle: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rack: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shelf: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bin: Mapped[str | None] = mapped_column(String(50), nullable=True)

    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    depth: Mapped[float | None] = mapped_column(Float, nullable=True)

    max_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    used_capacity: Mapped[float] = mapped_column(Float, default=0.0)

    storage_type: Mapped[str] = mapped_column(String(50), default="bin")
    accessibility_level: Mapped[int] = mapped_column(Integer, default=3)  # 1 (hardest) - 5 (easiest)

    dist_from_receiving: Mapped[float | None] = mapped_column(Float, nullable=True)
    dist_from_dispatch: Mapped[float | None] = mapped_column(Float, nullable=True)

    allowed_categories: Mapped[list] = mapped_column(JSON, default=list)
    temperature_restriction: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hazard_restriction: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fragility_restriction: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    zone: Mapped["Zone | None"] = relationship(back_populates="locations")

    __table_args__ = (UniqueConstraint("warehouse_id", "location_code", name="uq_location_warehouse_code"),)
