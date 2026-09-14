import uuid
from datetime import date as date_type, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# A forecast job covers one warehouse; sku_id is null when it forecasts every
# SKU with sales history in that warehouse. Real background-job stages per
# section 12 - the frontend polls `stage`, never a fake percentage.
JOB_STATUSES = {"queued", "running", "succeeded", "failed"}
JOB_STAGES = {"validating", "preparing", "training", "evaluating", "generating", "saving"}


class ForecastJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "forecast_jobs"

    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sku_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=True, index=True
    )
    horizon_days: Mapped[int] = mapped_column(Integer, default=14)

    status: Mapped[str] = mapped_column(String(20), default="queued")
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    skus_processed: Mapped[int] = mapped_column(Integer, default=0)
    skus_skipped: Mapped[int] = mapped_column(Integer, default=0)

    results: Mapped[list["ForecastResult"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    metrics: Mapped[list["ForecastModelMetric"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class ForecastResult(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "forecast_results"

    forecast_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecast_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), index=True, nullable=False
    )
    horizon_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    forecast_qty: Mapped[float] = mapped_column(Float, nullable=False)
    lower_ci: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_ci: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)

    job: Mapped["ForecastJob"] = relationship(back_populates="results")


class ForecastModelMetric(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "forecast_model_metrics"

    forecast_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecast_jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    mape: Mapped[float | None] = mapped_column(Float, nullable=True)
    wape: Mapped[float] = mapped_column(Float, nullable=False)
    bias: Mapped[float] = mapped_column(Float, nullable=False)
    is_chosen: Mapped[bool] = mapped_column(Boolean, default=False)

    job: Mapped["ForecastJob"] = relationship(back_populates="metrics")
