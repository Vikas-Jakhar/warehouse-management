import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.forecast import ForecastJob, ForecastModelMetric, ForecastResult
from app.models.sales import SalesRecord
from app.models.sku import Sku
from app.models.warehouse import Warehouse
from app.schemas.forecast import (
    ForecastJobOut,
    ForecastModelMetricOut,
    ForecastResultOut,
    ForecastSummaryItem,
    GenerateForecastRequest,
    HistoricalDemandPoint,
    PaginatedForecastSummary,
    SkuForecastDetail,
)
from app.services.tenancy import scoped
from app.tasks.forecasting_tasks import generate_forecasts_task

router = APIRouter(prefix="/api/v1/warehouses/{warehouse_id}/forecasts", tags=["forecasts"])


def _get_owned_warehouse(db: Session, customer_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")
    return warehouse


def _get_owned_job(db: Session, warehouse_id: uuid.UUID, job_id: uuid.UUID) -> ForecastJob:
    job = db.query(ForecastJob).filter(ForecastJob.id == job_id, ForecastJob.warehouse_id == warehouse_id).one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Forecast job not found")
    return job


@router.post("/generate", response_model=ForecastJobOut, status_code=status.HTTP_202_ACCEPTED)
def generate_forecasts(
    warehouse_id: uuid.UUID,
    payload: GenerateForecastRequest,
    current_user: CurrentUser = Depends(require_permission("forecast:generate")),
    db: Session = Depends(get_db),
) -> ForecastJob:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    if payload.sku_id is not None:
        sku = scoped(db.query(Sku), Sku, current_user.customer_id).filter(Sku.id == payload.sku_id).one_or_none()
        if sku is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "SKU not found")

    job = ForecastJob(warehouse_id=warehouse_id, sku_id=payload.sku_id, horizon_days=payload.horizon_days, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    generate_forecasts_task.delay(str(job.id))
    return job


@router.get("/jobs/{job_id}", response_model=ForecastJobOut)
def get_forecast_job(
    warehouse_id: uuid.UUID,
    job_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForecastJob:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    return _get_owned_job(db, warehouse_id, job_id)


@router.get("", response_model=PaginatedForecastSummary)
def list_forecast_summary(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedForecastSummary:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    latest_result_per_sku = (
        db.query(ForecastResult.sku_id, func.max(ForecastResult.created_at).label("latest"))
        .join(ForecastJob, ForecastJob.id == ForecastResult.forecast_job_id)
        .filter(ForecastJob.warehouse_id == warehouse_id)
        .group_by(ForecastResult.sku_id)
        .all()
    )

    items: list[ForecastSummaryItem] = []
    for sku_id, _latest in latest_result_per_sku:
        sku = db.get(Sku, sku_id)
        if sku is None:
            continue
        latest_job = (
            db.query(ForecastJob)
            .join(ForecastResult, ForecastResult.forecast_job_id == ForecastJob.id)
            .filter(ForecastJob.warehouse_id == warehouse_id, ForecastResult.sku_id == sku_id)
            .order_by(ForecastJob.finished_at.desc())
            .first()
        )
        chosen_metric = (
            db.query(ForecastModelMetric)
            .filter(
                ForecastModelMetric.forecast_job_id == latest_job.id,
                ForecastModelMetric.sku_id == sku_id,
                ForecastModelMetric.is_chosen.is_(True),
            )
            .first()
            if latest_job
            else None
        )
        last_forecast = (
            db.query(ForecastResult)
            .filter(ForecastResult.forecast_job_id == latest_job.id, ForecastResult.sku_id == sku_id)
            .order_by(ForecastResult.horizon_date.desc())
            .first()
            if latest_job
            else None
        )
        items.append(
            ForecastSummaryItem(
                sku_id=sku_id,
                sku_code=sku.sku_code,
                sku_name=sku.name,
                chosen_model=chosen_metric.model_name if chosen_metric else None,
                wape=chosen_metric.wape if chosen_metric else None,
                last_forecast_date=last_forecast.horizon_date if last_forecast else None,
                last_generated_at=latest_job.finished_at if latest_job else None,
            )
        )

    return PaginatedForecastSummary(items=items, total=len(items))


@router.get("/{sku_id}", response_model=SkuForecastDetail)
def get_forecast_detail(
    warehouse_id: uuid.UUID,
    sku_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SkuForecastDetail:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    sku = scoped(db.query(Sku), Sku, current_user.customer_id).filter(Sku.id == sku_id).one_or_none()
    if sku is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SKU not found")

    latest_job = (
        db.query(ForecastJob)
        .join(ForecastResult, ForecastResult.forecast_job_id == ForecastJob.id)
        .filter(ForecastJob.warehouse_id == warehouse_id, ForecastResult.sku_id == sku_id)
        .order_by(ForecastJob.finished_at.desc())
        .first()
    )

    forecast_rows: list[ForecastResultOut] = []
    metric_rows: list[ForecastModelMetricOut] = []
    chosen_model = None
    if latest_job is not None:
        forecast_rows = [
            ForecastResultOut.model_validate(r)
            for r in db.query(ForecastResult)
            .filter(ForecastResult.forecast_job_id == latest_job.id, ForecastResult.sku_id == sku_id)
            .order_by(ForecastResult.horizon_date)
            .all()
        ]
        metric_rows = [
            ForecastModelMetricOut.model_validate(m)
            for m in db.query(ForecastModelMetric)
            .filter(ForecastModelMetric.forecast_job_id == latest_job.id, ForecastModelMetric.sku_id == sku_id)
            .order_by(ForecastModelMetric.wape)
            .all()
        ]
        chosen = next((m for m in metric_rows if m.is_chosen), None)
        chosen_model = chosen.model_name if chosen else None

    historical = [
        HistoricalDemandPoint(date=r.sale_date, quantity_sold=r.quantity_sold)
        for r in db.query(SalesRecord)
        .filter(SalesRecord.warehouse_id == warehouse_id, SalesRecord.sku_id == sku_id)
        .order_by(SalesRecord.sale_date)
        .all()
    ]

    return SkuForecastDetail(
        sku_id=sku_id,
        sku_code=sku.sku_code,
        historical_demand=historical,
        forecast=forecast_rows,
        metrics=metric_rows,
        chosen_model=chosen_model,
        last_forecast_generated_at=latest_job.finished_at if latest_job else None,
    )
