from datetime import datetime

from pydantic import BaseModel


class RecentActivityItem(BaseModel):
    entity_type: str
    entity_id: str
    action: str
    created_at: datetime


class CustomerOverview(BaseModel):
    total_warehouses: int
    total_skus: int
    total_inventory_units: float
    pending_recommendations: int
    pending_movement_tasks: int
    recent_activity: list[RecentActivityItem]


class CategoryQuantity(BaseModel):
    category: str
    quantity: float


class DemandTrendPoint(BaseModel):
    date: str
    quantity_sold: float


class SkuVelocityEntry(BaseModel):
    sku_id: str
    sku_code: str
    name: str
    velocity_30d: float


class StockRiskEntry(SkuVelocityEntry):
    on_hand: float
    reorder_point: float | None = None
    max_qty: float | None = None


class AgingBucket(BaseModel):
    bucket: str
    quantity: float


class ExpiringInventoryEntry(BaseModel):
    sku_code: str
    name: str
    expiry_date: str
    quantity: float


class WarehouseOverview(BaseModel):
    storage_utilization_pct: float
    total_storage_locations: int
    occupied_storage_locations: int
    inventory_by_category: list[CategoryQuantity]
    demand_trend: list[DemandTrendPoint]
    fast_movers: list[SkuVelocityEntry]
    slow_movers: list[SkuVelocityEntry]
    stockout_risk_skus: list[StockRiskEntry]
    overstock_risk_skus: list[StockRiskEntry]
    inventory_aging: list[AgingBucket]
    expiring_inventory: list[ExpiringInventoryEntry]
    recommendation_status_counts: dict[str, int]
    movement_status_counts: dict[str, int]
    skus_with_sales_history: int
    skus_with_forecast: int
