"""Runs a queued ForecastJob end-to-end: loads sales history, runs the pure
forecasting pipeline per SKU, and persists results/metrics - updating the
job's `stage` at each real step along the way (never a fake percentage, per
section 12/19). This function is deliberately DB-session-owning and
self-contained so it can be called identically from a Celery worker process
or (in tests) synchronously in-process.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.forecast import ForecastJob, ForecastModelMetric, ForecastResult
from app.models.sales import SalesRecord
from app.models.sku import Sku
from app.services.forecasting.pipeline import run_forecast_for_sku


def _set_stage(db: Session, job: ForecastJob, stage: str) -> None:
    job.stage = stage
    db.commit()


def _customer_id_for_warehouse(db: Session, warehouse_id):
    from app.models.warehouse import Warehouse

    warehouse = db.get(Warehouse, warehouse_id)
    return warehouse.customer_id if warehouse else None


def run_forecast_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(ForecastJob, job_id)
        if job is None:
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        _set_stage(db, job, "validating")

        sku_query = db.query(Sku.id).filter(Sku.customer_id == _customer_id_for_warehouse(db, job.warehouse_id))
        if job.sku_id is not None:
            sku_query = sku_query.filter(Sku.id == job.sku_id)
        # Only forecast SKUs that actually have sales history in this warehouse.
        sku_ids_with_sales = {
            row[0]
            for row in db.query(SalesRecord.sku_id)
            .filter(SalesRecord.warehouse_id == job.warehouse_id)
            .distinct()
        }
        target_sku_ids = [sid for (sid,) in sku_query if sid in sku_ids_with_sales]

        if not target_sku_ids:
            job.status = "failed"
            job.error = "No SKUs with sales history found for this warehouse."
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        _set_stage(db, job, "preparing")

        processed = 0
        skipped = 0

        for sku_id in target_sku_ids:
            rows = (
                db.query(SalesRecord.sale_date, SalesRecord.quantity_sold)
                .filter(SalesRecord.warehouse_id == job.warehouse_id, SalesRecord.sku_id == sku_id)
                .all()
            )
            sales_rows = [(r[0], float(r[1])) for r in rows]

            _set_stage(db, job, "training")
            outcome = run_forecast_for_sku(str(sku_id), sales_rows, job.horizon_days)
            _set_stage(db, job, "evaluating")

            if outcome.skipped_reason is not None:
                skipped += 1
                continue

            for evaluation in outcome.evaluations:
                db.add(
                    ForecastModelMetric(
                        forecast_job_id=job.id,
                        sku_id=sku_id,
                        model_name=evaluation.model_name,
                        mae=evaluation.mae,
                        rmse=evaluation.rmse,
                        mape=evaluation.mape,
                        wape=evaluation.wape,
                        bias=evaluation.bias,
                        is_chosen=evaluation.chosen,
                    )
                )

            _set_stage(db, job, "generating")
            for horizon_date, forecast_qty, lower, upper in zip(
                outcome.horizon_dates, outcome.forecast_values, outcome.lower_ci, outcome.upper_ci
            ):
                db.add(
                    ForecastResult(
                        forecast_job_id=job.id,
                        sku_id=sku_id,
                        horizon_date=horizon_date,
                        forecast_qty=forecast_qty,
                        lower_ci=lower,
                        upper_ci=upper,
                        model_used=outcome.chosen_model or "naive",
                    )
                )
            processed += 1

        _set_stage(db, job, "saving")
        job.skus_processed = processed
        job.skus_skipped = skipped
        job.status = "succeeded"
        job.finished_at = datetime.now(timezone.utc)
        job.stage = None
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(ForecastJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()
