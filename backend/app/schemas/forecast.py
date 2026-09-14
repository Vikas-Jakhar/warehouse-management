import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class GenerateForecastRequest(BaseModel):
    sku_id: uuid.UUID | None = None
    horizon_days: int = Field(default=14, ge=1, le=90)


class ForecastJobOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    sku_id: uuid.UUID | None
    horizon_days: int
    status: str
    stage: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    skus_processed: int
    skus_skipped: int

    model_config = {"from_attributes": True}


class ForecastResultOut(BaseModel):
    model_config = {"from_attributes": True, "protected_namespaces": ()}

    horizon_date: date
    forecast_qty: float
    lower_ci: float | None
    upper_ci: float | None
    model_used: str


class ForecastModelMetricOut(BaseModel):
    model_config = {"from_attributes": True, "protected_namespaces": ()}

    model_name: str
    mae: float
    rmse: float
    mape: float | None
    wape: float
    bias: float
    is_chosen: bool


class HistoricalDemandPoint(BaseModel):
    date: date
    quantity_sold: float


class SkuForecastDetail(BaseModel):
    sku_id: uuid.UUID
    sku_code: str
    historical_demand: list[HistoricalDemandPoint]
    forecast: list[ForecastResultOut]
    metrics: list[ForecastModelMetricOut]
    chosen_model: str | None
    last_forecast_generated_at: datetime | None


class ForecastSummaryItem(BaseModel):
    sku_id: uuid.UUID
    sku_code: str
    sku_name: str
    chosen_model: str | None
    wape: float | None
    last_forecast_date: date | None
    last_generated_at: datetime | None


class PaginatedForecastSummary(BaseModel):
    items: list[ForecastSummaryItem]
    total: int
