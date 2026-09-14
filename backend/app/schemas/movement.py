import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AcceptRecommendationRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class RejectRecommendationRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=1000)
    comment: str | None = Field(default=None, max_length=1000)


class OverrideRecommendationRequest(BaseModel):
    override_location_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=1000)


class ConfirmMovementRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=1000)


class CancelMovementRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class MovementTaskOut(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    recommendation_id: uuid.UUID | None
    inventory_record_id: uuid.UUID
    sku_code: str
    sku_name: str
    from_location_code: str | None
    to_location_code: str
    status: str
    assigned_to: uuid.UUID | None
    created_at: datetime


class PaginatedMovementTasks(BaseModel):
    items: list[MovementTaskOut]
    total: int
    page: int
    page_size: int
