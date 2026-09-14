"""Aggregation queries backing the dashboard and reports pages (section 17).
Kept as plain functions over a session rather than an API-shaped return so
they're independently testable and reusable if a second consumer (e.g. a
scheduled export) needs the same numbers later.
"""

import uuid
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.forecast import ForecastJob, ForecastResult
from app.models.inventory import InventoryBatch, InventoryRecord
from app.models.movement import MovementTask
from app.models.recommendation import Recommendation
from app.models.sales import SalesRecord
from app.models.sku import Sku
from app.models.warehouse import Warehouse
from app.models.warehouse_layout import StorageLocation

FAST_MOVER_PERCENTILE = 0.7
SLOW_MOVER_PERCENTILE = 0.3
AGING_BUCKETS = [(0, 30), (31, 60), (61, 90), (91, None)]
EXPIRY_WARNING_DAYS = 30


def customer_overview(db: Session, customer_id: uuid.UUID) -> dict:
    total_warehouses = db.query(Warehouse).filter(Warehouse.customer_id == customer_id, Warehouse.is_active.is_(True)).count()
    total_skus = db.query(Sku).filter(Sku.customer_id == customer_id, Sku.is_active.is_(True)).count()

    warehouse_ids = [w.id for w in db.query(Warehouse.id).filter(Warehouse.customer_id == customer_id)]
    total_inventory_units = (
        db.query(func.coalesce(func.sum(InventoryRecord.quantity), 0.0))
        .filter(InventoryRecord.warehouse_id.in_(warehouse_ids))
        .scalar()
        if warehouse_ids
        else 0.0
    )
    pending_recommendations = (
        db.query(Recommendation)
        .filter(Recommendation.warehouse_id.in_(warehouse_ids), Recommendation.status == "pending_review")
        .count()
        if warehouse_ids
        else 0
    )
    pending_movements = (
        db.query(MovementTask)
        .filter(MovementTask.warehouse_id.in_(warehouse_ids), MovementTask.status.in_(["pending", "in_progress"]))
        .count()
        if warehouse_ids
        else 0
    )

    recent_activity = (
        db.query(AuditLog)
        .filter(AuditLog.customer_id == customer_id)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "total_warehouses": total_warehouses,
        "total_skus": total_skus,
        "total_inventory_units": float(total_inventory_units),
        "pending_recommendations": pending_recommendations,
        "pending_movement_tasks": pending_movements,
        "recent_activity": [
            {
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "action": a.action,
                "created_at": a.created_at,
            }
            for a in recent_activity
        ],
    }


def _percentile_thresholds(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    fast_idx = min(n - 1, int(n * FAST_MOVER_PERCENTILE))
    slow_idx = max(0, int(n * SLOW_MOVER_PERCENTILE) - 1)
    return sorted_vals[slow_idx], sorted_vals[fast_idx]


def warehouse_overview(db: Session, warehouse_id: uuid.UUID) -> dict:
    # --- storage utilization: proportion of active storage locations that
    # currently hold at least one inventory record. A coarser proxy than true
    # weight/volume utilization (used_capacity isn't wired to real quantities
    # anywhere in this codebase yet), but it's a real, honestly-labeled number.
    total_storage_locations = (
        db.query(StorageLocation)
        .filter(
            StorageLocation.warehouse_id == warehouse_id,
            StorageLocation.location_type == "storage",
            StorageLocation.is_active.is_(True),
        )
        .count()
    )
    occupied_location_ids = {
        r[0]
        for r in db.query(InventoryRecord.current_location_id)
        .filter(InventoryRecord.warehouse_id == warehouse_id, InventoryRecord.current_location_id.isnot(None))
        .distinct()
    }
    storage_utilization_pct = (
        round(100.0 * len(occupied_location_ids) / total_storage_locations, 1) if total_storage_locations else 0.0
    )

    # --- inventory by category
    category_rows = (
        db.query(Sku.category, func.coalesce(func.sum(InventoryRecord.quantity), 0.0))
        .join(InventoryRecord, InventoryRecord.sku_id == Sku.id)
        .filter(InventoryRecord.warehouse_id == warehouse_id)
        .group_by(Sku.category)
        .all()
    )
    inventory_by_category = [{"category": cat or "Uncategorized", "quantity": float(qty)} for cat, qty in category_rows]

    # --- demand trend: total quantity sold per day, last 30 days
    since = date.today() - timedelta(days=30)
    demand_rows = (
        db.query(SalesRecord.sale_date, func.coalesce(func.sum(SalesRecord.quantity_sold), 0.0))
        .filter(SalesRecord.warehouse_id == warehouse_id, SalesRecord.sale_date >= since)
        .group_by(SalesRecord.sale_date)
        .order_by(SalesRecord.sale_date)
        .all()
    )
    demand_trend = [{"date": d.isoformat(), "quantity_sold": float(q)} for d, q in demand_rows]

    # --- SKU velocity classification (fast/medium/slow) from last-30-day sales
    velocity_rows = (
        db.query(SalesRecord.sku_id, func.coalesce(func.sum(SalesRecord.quantity_sold), 0.0))
        .filter(SalesRecord.warehouse_id == warehouse_id, SalesRecord.sale_date >= since)
        .group_by(SalesRecord.sku_id)
        .all()
    )
    velocity_by_sku = {sku_id: float(qty) for sku_id, qty in velocity_rows}
    slow_threshold, fast_threshold = _percentile_thresholds(list(velocity_by_sku.values()))

    fast_movers: list[dict] = []
    slow_movers: list[dict] = []
    stockout_risk: list[dict] = []
    overstock_risk: list[dict] = []

    sku_ids_in_warehouse = {
        r[0]
        for r in db.query(InventoryRecord.sku_id).filter(InventoryRecord.warehouse_id == warehouse_id).distinct()
    }
    skus_in_warehouse = db.query(Sku).filter(Sku.id.in_(sku_ids_in_warehouse)).all() if sku_ids_in_warehouse else []
    inventory_totals = dict(
        db.query(InventoryRecord.sku_id, func.coalesce(func.sum(InventoryRecord.quantity), 0.0))
        .filter(InventoryRecord.warehouse_id == warehouse_id)
        .group_by(InventoryRecord.sku_id)
        .all()
    )

    for sku in skus_in_warehouse:
        velocity = velocity_by_sku.get(sku.id, 0.0)
        entry = {"sku_id": str(sku.id), "sku_code": sku.sku_code, "name": sku.name, "velocity_30d": velocity}
        if velocity >= fast_threshold and velocity > 0:
            fast_movers.append(entry)
        elif velocity <= slow_threshold:
            slow_movers.append(entry)

        total_qty = float(inventory_totals.get(sku.id, 0.0))
        if sku.reorder_point is not None and total_qty <= sku.reorder_point:
            stockout_risk.append({**entry, "on_hand": total_qty, "reorder_point": sku.reorder_point})
        if sku.max_qty is not None and total_qty > sku.max_qty:
            overstock_risk.append({**entry, "on_hand": total_qty, "max_qty": sku.max_qty})

    # --- inventory aging (days since receipt, bucketed)
    aging_counts = {(f"{lo}-{hi}" if hi else f"{lo}+"): 0.0 for lo, hi in AGING_BUCKETS}
    today = date.today()
    batch_rows = (
        db.query(InventoryBatch.receiving_date, InventoryRecord.quantity)
        .join(InventoryRecord, InventoryRecord.batch_id == InventoryBatch.id)
        .filter(InventoryRecord.warehouse_id == warehouse_id)
        .all()
    )
    for receiving_date, qty in batch_rows:
        age_days = (today - receiving_date).days
        for lo, hi in AGING_BUCKETS:
            if age_days >= lo and (hi is None or age_days <= hi):
                aging_counts[f"{lo}-{hi}" if hi else f"{lo}+"] += float(qty)
                break

    # --- expiring inventory (within warning window)
    expiry_cutoff = today + timedelta(days=EXPIRY_WARNING_DAYS)
    expiring_rows = (
        db.query(Sku.sku_code, Sku.name, InventoryBatch.expiry_date, InventoryRecord.quantity)
        .join(InventoryRecord, InventoryRecord.batch_id == InventoryBatch.id)
        .join(Sku, Sku.id == InventoryRecord.sku_id)
        .filter(
            InventoryRecord.warehouse_id == warehouse_id,
            InventoryBatch.expiry_date.isnot(None),
            InventoryBatch.expiry_date <= expiry_cutoff,
        )
        .order_by(InventoryBatch.expiry_date)
        .all()
    )
    expiring_inventory = [
        {"sku_code": code, "name": name, "expiry_date": exp.isoformat(), "quantity": float(qty)}
        for code, name, exp, qty in expiring_rows
    ]

    # --- recommendation and movement status breakdowns
    rec_status_rows = (
        db.query(Recommendation.status, func.count(Recommendation.id))
        .filter(Recommendation.warehouse_id == warehouse_id)
        .group_by(Recommendation.status)
        .all()
    )
    recommendation_status_counts = {status: count for status, count in rec_status_rows}

    movement_status_rows = (
        db.query(MovementTask.status, func.count(MovementTask.id))
        .filter(MovementTask.warehouse_id == warehouse_id)
        .group_by(MovementTask.status)
        .all()
    )
    movement_status_counts = {status: count for status, count in movement_status_rows}

    # --- forecast coverage
    skus_with_sales = {
        r[0] for r in db.query(SalesRecord.sku_id).filter(SalesRecord.warehouse_id == warehouse_id).distinct()
    }
    skus_forecasted = {
        r[0]
        for r in db.query(ForecastResult.sku_id)
        .join(ForecastJob, ForecastJob.id == ForecastResult.forecast_job_id)
        .filter(ForecastJob.warehouse_id == warehouse_id, ForecastJob.status == "succeeded")
        .distinct()
    }

    return {
        "storage_utilization_pct": storage_utilization_pct,
        "total_storage_locations": total_storage_locations,
        "occupied_storage_locations": len(occupied_location_ids),
        "inventory_by_category": inventory_by_category,
        "demand_trend": demand_trend,
        "fast_movers": sorted(fast_movers, key=lambda x: -x["velocity_30d"])[:10],
        "slow_movers": sorted(slow_movers, key=lambda x: x["velocity_30d"])[:10],
        "stockout_risk_skus": stockout_risk,
        "overstock_risk_skus": overstock_risk,
        "inventory_aging": [{"bucket": k, "quantity": v} for k, v in aging_counts.items()],
        "expiring_inventory": expiring_inventory,
        "recommendation_status_counts": recommendation_status_counts,
        "movement_status_counts": movement_status_counts,
        "skus_with_sales_history": len(skus_with_sales),
        "skus_with_forecast": len(skus_forecasted),
    }
