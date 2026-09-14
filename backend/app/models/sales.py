import uuid
from datetime import date as date_type

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class SalesRecord(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sales_records"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), index=True, nullable=False
    )

    sale_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    quantity_sold: Mapped[float] = mapped_column(Float, nullable=False)

    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_segment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sales_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    promotion: Mapped[bool] = mapped_column(Boolean, default=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount: Mapped[float | None] = mapped_column(Float, nullable=True)
    holiday_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    returns: Mapped[float] = mapped_column(Float, default=0.0)
    stockout_flag: Mapped[bool] = mapped_column(Boolean, default=False)
