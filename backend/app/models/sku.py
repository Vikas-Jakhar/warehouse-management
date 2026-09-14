import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

FRAGILITY_LEVELS = {"none", "low", "medium", "high"}
HAZARD_CLASSES = {"none", "flammable", "corrosive", "toxic", "oxidizer", "compressed_gas"}


class Sku(UUIDPKMixin, TimestampMixin, Base):
    """Product master data. SKUs belong to a customer, not a single warehouse -
    the same SKU can be stocked (and slotted independently) across multiple
    warehouses, per spec section 8.
    """

    __tablename__ = "skus"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )

    sku_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uom: Mapped[str] = mapped_column(String(20), default="each")

    length: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)

    storage_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    temperature_requirement: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fragility: Mapped[str] = mapped_column(String(20), default="none")
    hazard_class: Mapped[str] = mapped_column(String(50), default="none")

    min_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    reorder_point: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_stock: Mapped[float | None] = mapped_column(Float, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_expiry: Mapped[bool] = mapped_column(Boolean, default=False)

    preferred_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True
    )
    picking_priority: Mapped[int] = mapped_column(Integer, default=3)

    fifo_required: Mapped[bool] = mapped_column(Boolean, default=True)
    fefo_required: Mapped[bool] = mapped_column(Boolean, default=False)
    lifo_permitted: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("customer_id", "sku_code", name="uq_sku_customer_code"),)
