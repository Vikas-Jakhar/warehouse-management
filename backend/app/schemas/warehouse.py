import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    address: str | None = None
    warehouse_type: str = "general"
    total_area: float | None = Field(default=None, ge=0)
    operating_hours: dict[str, Any] = Field(default_factory=dict)
    storage_capacity: float | None = Field(default=None, ge=0)
    default_inventory_policy: str = "FIFO"
    default_picking_policy: str = "standard"
    default_replenishment_policy: str = "reorder_point"

    @field_validator("default_inventory_policy")
    @classmethod
    def validate_policy(cls, v: str) -> str:
        allowed = {"FIFO", "FEFO", "LIFO"}
        if v.upper() not in allowed:
            raise ValueError(f"policy must be one of {allowed}")
        return v.upper()


class WarehouseUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    warehouse_type: str | None = None
    total_area: float | None = Field(default=None, ge=0)
    operating_hours: dict[str, Any] | None = None
    storage_capacity: float | None = Field(default=None, ge=0)
    default_inventory_policy: str | None = None
    default_picking_policy: str | None = None
    default_replenishment_policy: str | None = None
    is_active: bool | None = None


class WarehouseOut(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    address: str | None
    warehouse_type: str
    total_area: float | None
    operating_hours: dict[str, Any]
    storage_capacity: float | None
    default_inventory_policy: str
    default_picking_policy: str
    default_replenishment_policy: str
    is_active: bool

    model_config = {"from_attributes": True}


class PaginatedWarehouses(BaseModel):
    items: list[WarehouseOut]
    total: int
    page: int
    page_size: int
