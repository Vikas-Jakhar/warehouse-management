"""Runs a queued RecommendationJob end-to-end. Mirrors the forecast job
runner's shape: DB-session-owning, self-contained, callable identically from
a Celery worker or synchronously in tests.

Stability handling (section 14): a fresh run never blindly appends duplicate
recommendations. For each inventory record evaluated this run:
  - if an existing `pending_review` recommendation for it points at the same
    location, it's left untouched (no duplicate, no busywork for the manager)
  - if it now points at a different (better) location, the old one is
    superseded (`expired`) and a new one is created
  - if the record was rejected within the cooldown window, it's skipped
    entirely unless a caller explicitly forces re-evaluation
  - any previously pending_review recommendation whose inventory record
    *isn't* re-recommended this run (now well-placed, or no longer eligible)
    is also expired, so the open queue always reflects current reality
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.forecast import ForecastJob, ForecastModelMetric, ForecastResult
from app.models.inventory import InventoryRecord
from app.models.recommendation import Recommendation, RecommendationDecision, RecommendationJob
from app.models.sales import SalesRecord
from app.models.sku import Sku
from app.models.warehouse_layout import StorageLocation
from app.services.slotting.engine import (
    InventoryRecordInput,
    LocationInput,
    SkuInput,
    generate_recommendations,
)

REJECTION_COOLDOWN_DAYS = 14


def _set_stage(db: Session, job: RecommendationJob, stage: str) -> None:
    job.stage = stage
    db.commit()


def _demand_velocity_and_confidence(db: Session, warehouse_id, sku_ids: set) -> tuple[dict, dict]:
    velocity: dict = {}
    confidence: dict = {}
    since = datetime.now(timezone.utc).date() - timedelta(days=30)

    for sku_id in sku_ids:
        latest_forecast_job = (
            db.query(ForecastJob)
            .join(ForecastResult, ForecastResult.forecast_job_id == ForecastJob.id)
            .filter(ForecastJob.warehouse_id == warehouse_id, ForecastResult.sku_id == sku_id, ForecastJob.status == "succeeded")
            .order_by(ForecastJob.finished_at.desc())
            .first()
        )
        if latest_forecast_job is not None:
            avg_forecast = (
                db.query(ForecastResult)
                .filter(ForecastResult.forecast_job_id == latest_forecast_job.id, ForecastResult.sku_id == sku_id)
                .all()
            )
            if avg_forecast:
                velocity[sku_id] = sum(r.forecast_qty for r in avg_forecast) / len(avg_forecast)
                chosen_metric = (
                    db.query(ForecastModelMetric)
                    .filter(
                        ForecastModelMetric.forecast_job_id == latest_forecast_job.id,
                        ForecastModelMetric.sku_id == sku_id,
                        ForecastModelMetric.is_chosen.is_(True),
                    )
                    .first()
                )
                confidence[sku_id] = max(0.5, min(0.95, 1.0 - chosen_metric.wape)) if chosen_metric else 0.7
                continue

        recent_sales = (
            db.query(SalesRecord)
            .filter(SalesRecord.sku_id == sku_id, SalesRecord.sale_date >= since)
            .all()
        )
        if recent_sales:
            velocity[sku_id] = sum(r.quantity_sold for r in recent_sales) / 30.0
            confidence[sku_id] = min(0.85, 0.3 + 0.02 * len(recent_sales))
        else:
            velocity[sku_id] = 0.0
            confidence[sku_id] = 0.5  # neutral - no history yet, but put-away still needs a home

    return velocity, confidence


def run_recommendation_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(RecommendationJob, job_id)
        if job is None:
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        _set_stage(db, job, "validating")

        inventory_rows = (
            db.query(InventoryRecord)
            .filter(
                InventoryRecord.warehouse_id == job.warehouse_id,
                InventoryRecord.status.in_(["in_stock", "awaiting_putaway"]),
            )
            .all()
        )
        if not inventory_rows:
            job.status = "failed"
            job.error = "No in-stock or awaiting-putaway inventory found for this warehouse."
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        sku_ids = {r.sku_id for r in inventory_rows}
        skus_by_id = {
            s.id: SkuInput(
                id=s.id,
                sku_code=s.sku_code,
                weight=s.weight,
                volume=s.volume,
                category=s.category,
                temperature_requirement=s.temperature_requirement,
                fragility=s.fragility,
                hazard_class=s.hazard_class,
                picking_priority=s.picking_priority,
            )
            for s in db.query(Sku).filter(Sku.id.in_(sku_ids)).all()
        }

        locations = [
            LocationInput(
                id=loc.id,
                location_code=loc.location_code,
                x=loc.x,
                y=loc.y,
                max_weight=loc.max_weight,
                max_volume=loc.max_volume,
                used_capacity=loc.used_capacity,
                allowed_categories=loc.allowed_categories or [],
                temperature_restriction=loc.temperature_restriction,
                hazard_restriction=loc.hazard_restriction,
                fragility_restriction=loc.fragility_restriction,
                is_active=loc.is_active,
                is_blocked=loc.is_blocked,
                is_available=loc.is_available,
                location_type=loc.location_type,
                accessibility_level=loc.accessibility_level,
            )
            for loc in db.query(StorageLocation).filter(StorageLocation.warehouse_id == job.warehouse_id).all()
        ]

        receiving = (
            db.query(StorageLocation)
            .filter(StorageLocation.warehouse_id == job.warehouse_id, StorageLocation.location_type == "receiving")
            .order_by(StorageLocation.created_at)
            .first()
        )
        dispatch = (
            db.query(StorageLocation)
            .filter(StorageLocation.warehouse_id == job.warehouse_id, StorageLocation.location_type == "dispatch")
            .order_by(StorageLocation.created_at)
            .first()
        )
        receiving_point = (receiving.x, receiving.y) if receiving else None
        dispatch_point = (dispatch.x, dispatch.y) if dispatch else None

        _set_stage(db, job, "scoring")
        demand_velocity_by_sku, confidence_by_sku = _demand_velocity_and_confidence(db, job.warehouse_id, sku_ids)

        _set_stage(db, job, "applying_stability_rules")

        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=REJECTION_COOLDOWN_DAYS)
        recently_rejected = (
            db.query(RecommendationDecision.recommendation_id)
            .join(Recommendation, Recommendation.id == RecommendationDecision.recommendation_id)
            .filter(RecommendationDecision.decision == "reject", RecommendationDecision.decided_at >= cooldown_cutoff)
            .all()
        )
        rejected_recommendation_ids = {r[0] for r in recently_rejected}
        suppressed_inventory_record_ids = {
            rec.inventory_record_id
            for rec in db.query(Recommendation).filter(Recommendation.id.in_(rejected_recommendation_ids)).all()
        }

        existing_open = {
            rec.inventory_record_id: rec
            for rec in db.query(Recommendation).filter(
                Recommendation.warehouse_id == job.warehouse_id, Recommendation.status == "pending_review"
            )
        }

        candidates = generate_recommendations(
            inventory_records=[
                InventoryRecordInput(
                    id=r.id, sku_id=r.sku_id, current_location_id=r.current_location_id, quantity=r.quantity, status=r.status
                )
                for r in inventory_rows
            ],
            skus_by_id=skus_by_id,
            locations=locations,
            demand_velocity_by_sku=demand_velocity_by_sku,
            confidence_by_sku=confidence_by_sku,
            receiving_point=receiving_point,
            dispatch_point=dispatch_point,
            suppressed_inventory_record_ids=suppressed_inventory_record_ids,
        )

        _set_stage(db, job, "saving")

        created = 0
        renewed_inventory_record_ids = set()
        for candidate in candidates:
            renewed_inventory_record_ids.add(candidate.inventory_record_id)
            existing = existing_open.get(candidate.inventory_record_id)
            if existing is not None:
                if existing.recommended_location_id == candidate.recommended_location_id:
                    continue  # unchanged - leave the existing recommendation as-is
                existing.status = "expired"  # superseded by new information

            db.add(
                Recommendation(
                    warehouse_id=job.warehouse_id,
                    sku_id=candidate.sku_id,
                    inventory_record_id=candidate.inventory_record_id,
                    current_location_id=candidate.current_location_id,
                    recommended_location_id=candidate.recommended_location_id,
                    reason=candidate.reasons,
                    expected_benefit=candidate.expected_benefit,
                    distance_reduction=candidate.distance_reduction,
                    demand_classification=candidate.demand_classification,
                    confidence_score=candidate.confidence_score,
                    status="pending_review",
                )
            )
            created += 1

        # Anything still open but not renewed this run is stale - expire it.
        for inventory_record_id, rec in existing_open.items():
            if inventory_record_id not in renewed_inventory_record_ids:
                rec.status = "expired"

        job.recommendations_created = created
        job.inventory_records_evaluated = len(inventory_rows)
        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        job.stage = None
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(RecommendationJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()
