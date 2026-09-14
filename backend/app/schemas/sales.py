import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel


class SalesRecordOut(BaseModel):
    id: uuid.UUID
    sku_id: uuid.UUID
    sale_date: date
    quantity_sold: float
    order_id: str | None
    customer_segment: str | None
    sales_channel: str | None
    region: str | None
    promotion: bool
    price: float | None
    discount: float | None
    holiday_flag: bool
    returns: float
    stockout_flag: bool

    model_config = {"from_attributes": True}


class PaginatedSalesRecords(BaseModel):
    items: list[SalesRecordOut]
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
