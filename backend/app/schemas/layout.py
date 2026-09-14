import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.warehouse_layout import LOCATION_TYPES, STORAGE_TYPES, ZONE_TYPES


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    zone_code: str = Field(min_length=1, max_length=50)
    zone_type: str
    temperature_min: float | None = None
    temperature_max: float | None = None
    hazard_class: str | None = None

    @field_validator("zone_type")
    @classmethod
    def validate_zone_type(cls, v: str) -> str:
        if v not in ZONE_TYPES:
            raise ValueError(f"zone_type must be one of {sorted(ZONE_TYPES)}")
        return v


class ZoneOut(BaseModel):
    id: uuid.UUID
    name: str
    zone_code: str
    zone_type: str
    temperature_min: float | None
    temperature_max: float | None
    hazard_class: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class StorageLocationCreate(BaseModel):
    location_code: str = Field(min_length=1, max_length=100)
    location_type: str = "storage"
    zone_id: uuid.UUID | None = None
    aisle: str | None = None
    rack: str | None = None
    shelf: str | None = None
    bin: str | None = None
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    depth: float | None = Field(default=None, ge=0)
    max_weight: float | None = Field(default=None, ge=0)
    max_volume: float | None = Field(default=None, ge=0)
    storage_type: str = "bin"
    accessibility_level: int = Field(default=3, ge=1, le=5)
    allowed_categories: list[str] = Field(default_factory=list)
    temperature_restriction: str | None = None
    hazard_restriction: str | None = None
    fragility_restriction: str | None = None

    @field_validator("location_type")
    @classmethod
    def validate_location_type(cls, v: str) -> str:
        if v not in LOCATION_TYPES:
            raise ValueError(f"location_type must be one of {sorted(LOCATION_TYPES)}")
        return v

    @field_validator("storage_type")
    @classmethod
    def validate_storage_type(cls, v: str) -> str:
        if v not in STORAGE_TYPES:
            raise ValueError(f"storage_type must be one of {sorted(STORAGE_TYPES)}")
        return v


class StorageLocationUpdate(BaseModel):
    zone_id: uuid.UUID | None = None
    x: float | None = Field(default=None, ge=0)
    y: float | None = Field(default=None, ge=0)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    is_active: bool | None = None
    is_blocked: bool | None = None
    is_available: bool | None = None


class StorageLocationOut(BaseModel):
    id: uuid.UUID
    zone_id: uuid.UUID | None
    location_code: str
    location_type: str
    aisle: str | None
    rack: str | None
    shelf: str | None
    bin: str | None
    x: float
    y: float
    width: float
    height: float
    depth: float | None
    max_weight: float | None
    max_volume: float | None
    used_capacity: float
    storage_type: str
    accessibility_level: int
    allowed_categories: list[Any]
    temperature_restriction: str | None
    hazard_restriction: str | None
    fragility_restriction: str | None
    is_active: bool
    is_blocked: bool
    is_available: bool

    model_config = {"from_attributes": True}


class LayoutValidationResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    is_valid: bool
    errors: list[dict[str, Any]]
    committed: bool
    locations_created: int
    zones_created: int
    error_report_csv: str | None = None
