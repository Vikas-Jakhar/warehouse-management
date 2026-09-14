import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel


class InventoryRecordOut(BaseModel):
    id: uuid.UUID
    sku_id: uuid.UUID
    batch_id: uuid.UUID | None
    current_location_id: uuid.UUID | None
    quantity: float
    reserved_quantity: float
    damaged_quantity: float
    available_quantity: float
    status: str

    model_config = {"from_attributes": True}


class PaginatedInventoryRecords(BaseModel):
    items: list[InventoryRecordOut]
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
