import uuid
from datetime import datetime

from pydantic import BaseModel


class RecommendationJobOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    status: str
    stage: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    recommendations_created: int
    inventory_records_evaluated: int

    model_config = {"from_attributes": True}


class RecommendationOut(BaseModel):
    id: uuid.UUID
    sku_id: uuid.UUID
    sku_code: str
    sku_name: str
    inventory_record_id: uuid.UUID
    current_location_id: uuid.UUID | None
    current_location_code: str | None
    recommended_location_id: uuid.UUID
    recommended_location_code: str
    reason: list[str]
    expected_benefit: float
    distance_reduction: float | None
    demand_classification: str
    confidence_score: float
    requires_approval: bool
    status: str
    created_at: datetime


class PaginatedRecommendations(BaseModel):
    items: list[RecommendationOut]
    total: int
    page: int
    page_size: int
