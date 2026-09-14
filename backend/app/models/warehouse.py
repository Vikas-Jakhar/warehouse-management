import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Warehouse(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "warehouses"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    warehouse_type: Mapped[str] = mapped_column(String(50), default="general")
    total_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    operating_hours: Mapped[dict] = mapped_column(JSON, default=dict)
    storage_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)

    default_inventory_policy: Mapped[str] = mapped_column(String(20), default="FIFO")
    default_picking_policy: Mapped[str] = mapped_column(String(50), default="standard")
    default_replenishment_policy: Mapped[str] = mapped_column(String(50), default="reorder_point")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    customer: Mapped["Customer"] = relationship(back_populates="warehouses")  # noqa: F821

    __table_args__ = (UniqueConstraint("customer_id", "code", name="uq_warehouse_customer_code"),)
