import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.sku import FRAGILITY_LEVELS, HAZARD_CLASSES


class SKUCreate(BaseModel):
    sku_code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    uom: str = "each"

    length: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, ge=0)
    height: float | None = Field(default=None, ge=0)
    weight: float | None = Field(default=None, ge=0)
    volume: float | None = Field(default=None, ge=0)

    temperature_requirement: str | None = None
    fragility: str = "none"
    hazard_class: str = "none"

    min_qty: float | None = Field(default=None, ge=0)
    max_qty: float | None = Field(default=None, ge=0)
    reorder_point: float | None = Field(default=None, ge=0)
    safety_stock: float | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    shelf_life_days: int | None = Field(default=None, ge=0)
    requires_expiry: bool = False

    preferred_zone_id: uuid.UUID | None = None
    picking_priority: int = Field(default=3, ge=1, le=5)

    fifo_required: bool = True
    fefo_required: bool = False
    lifo_permitted: bool = False

    @field_validator("fragility")
    @classmethod
    def validate_fragility(cls, v: str) -> str:
        if v not in FRAGILITY_LEVELS:
            raise ValueError(f"fragility must be one of {sorted(FRAGILITY_LEVELS)}")
        return v

    @field_validator("hazard_class")
    @classmethod
    def validate_hazard_class(cls, v: str) -> str:
        if v not in HAZARD_CLASSES:
            raise ValueError(f"hazard_class must be one of {sorted(HAZARD_CLASSES)}")
        return v

    @field_validator("fefo_required")
    @classmethod
    def validate_fefo_requires_expiry(cls, v: bool, info) -> bool:
        if v and info.data.get("requires_expiry") is False:
            raise ValueError("fefo_required cannot be true when requires_expiry is false")
        return v


class SKUUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    reorder_point: float | None = Field(default=None, ge=0)
    safety_stock: float | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    picking_priority: int | None = Field(default=None, ge=1, le=5)
    fifo_required: bool | None = None
    fefo_required: bool | None = None
    lifo_permitted: bool | None = None
    is_active: bool | None = None


class SKUOut(BaseModel):
    id: uuid.UUID
    sku_code: str
    name: str
    description: str | None
    category: str | None
    subcategory: str | None
    brand: str | None
    uom: str
    length: float | None
    width: float | None
    height: float | None
    weight: float | None
    volume: float | None
    temperature_requirement: str | None
    fragility: str
    hazard_class: str
    min_qty: float | None
    max_qty: float | None
    reorder_point: float | None
    safety_stock: float | None
    lead_time_days: int | None
    shelf_life_days: int | None
    requires_expiry: bool
    preferred_zone_id: uuid.UUID | None
    picking_priority: int
    fifo_required: bool
    fefo_required: bool
    lifo_permitted: bool
    is_active: bool

    model_config = {"from_attributes": True}


class PaginatedSKUs(BaseModel):
    items: list[SKUOut]
    total: int
    page: int
    page_size: int


class BulkUploadResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    is_valid: bool
    errors: list[dict[str, Any]]
    committed: bool
    records_created: int
    error_report_csv: str | None = None
