import uuid

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.recommendation import Recommendation, RecommendationJob
from app.models.sku import Sku
from app.models.warehouse import Warehouse
from app.models.warehouse_layout import StorageLocation
from app.schemas.movement import (
    AcceptRecommendationRequest,
    MovementTaskOut,
    OverrideRecommendationRequest,
    RejectRecommendationRequest,
)
from app.schemas.recommendation import PaginatedRecommendations, RecommendationJobOut, RecommendationOut
from app.services.movement_workflow import serialize_movement_task
from app.services.recommendation_workflow import accept_recommendation, override_recommendation, reject_recommendation
from app.services.tenancy import scoped
from app.tasks.slotting_tasks import generate_recommendations_task

router = APIRouter(prefix="/api/v1/warehouses/{warehouse_id}/recommendations", tags=["recommendations"])


def _get_owned_warehouse(db: Session, customer_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")
    return warehouse


@router.post("/generate", response_model=RecommendationJobOut, status_code=status.HTTP_202_ACCEPTED)
def generate_recommendations_endpoint(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("recommendation:approve")),
    db: Session = Depends(get_db),
) -> RecommendationJob:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    job = RecommendationJob(warehouse_id=warehouse_id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    generate_recommendations_task.delay(str(job.id))
    return job


@router.get("/jobs/{job_id}", response_model=RecommendationJobOut)
def get_recommendation_job(
    warehouse_id: uuid.UUID,
    job_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationJob:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    job = (
        db.query(RecommendationJob)
        .filter(RecommendationJob.id == job_id, RecommendationJob.warehouse_id == warehouse_id)
        .one_or_none()
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation job not found")
    return job


@router.get("", response_model=PaginatedRecommendations)
def list_recommendations(
    warehouse_id: uuid.UUID,
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
    status_filter: str | None = QueryParam(None, alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedRecommendations:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    query = db.query(Recommendation).filter(Recommendation.warehouse_id == warehouse_id)
    query = query.filter(Recommendation.status == status_filter) if status_filter else query.filter(
        Recommendation.status == "pending_review"
    )
    total = query.count()
    rows = query.order_by(Recommendation.expected_benefit.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items: list[RecommendationOut] = []
    for rec in rows:
        sku = db.get(Sku, rec.sku_id)
        recommended_loc = db.get(StorageLocation, rec.recommended_location_id)
        current_loc = db.get(StorageLocation, rec.current_location_id) if rec.current_location_id else None
        items.append(
            RecommendationOut(
                id=rec.id,
                sku_id=rec.sku_id,
                sku_code=sku.sku_code if sku else "?",
                sku_name=sku.name if sku else "?",
                inventory_record_id=rec.inventory_record_id,
                current_location_id=rec.current_location_id,
                current_location_code=current_loc.location_code if current_loc else None,
                recommended_location_id=rec.recommended_location_id,
                recommended_location_code=recommended_loc.location_code if recommended_loc else "?",
                reason=rec.reason,
                expected_benefit=rec.expected_benefit,
                distance_reduction=rec.distance_reduction,
                demand_classification=rec.demand_classification,
                confidence_score=rec.confidence_score,
                requires_approval=rec.requires_approval,
                status=rec.status,
                created_at=rec.created_at,
            )
        )

    return PaginatedRecommendations(items=items, total=total, page=page, page_size=page_size)


def _get_owned_recommendation(db: Session, warehouse_id: uuid.UUID, recommendation_id: uuid.UUID) -> Recommendation:
    rec = (
        db.query(Recommendation)
        .filter(Recommendation.id == recommendation_id, Recommendation.warehouse_id == warehouse_id)
        .one_or_none()
    )
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    return rec


@router.post("/{recommendation_id}/accept", response_model=MovementTaskOut, status_code=status.HTTP_201_CREATED)
def accept_recommendation_endpoint(
    warehouse_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    payload: AcceptRecommendationRequest,
    current_user: CurrentUser = Depends(require_permission("recommendation:approve")),
    db: Session = Depends(get_db),
) -> MovementTaskOut:

    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    rec = _get_owned_recommendation(db, warehouse_id, recommendation_id)
    movement = accept_recommendation(
        db, rec, user_id=current_user.id, customer_id=current_user.customer_id, comment=payload.comment
    )
    return serialize_movement_task(db, movement)


@router.post("/{recommendation_id}/reject", response_model=RecommendationOut)
def reject_recommendation_endpoint(
    warehouse_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    payload: RejectRecommendationRequest,
    current_user: CurrentUser = Depends(require_permission("recommendation:approve")),
    db: Session = Depends(get_db),
) -> RecommendationOut:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    rec = _get_owned_recommendation(db, warehouse_id, recommendation_id)
    rec = reject_recommendation(
        db,
        rec,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
        rejection_reason=payload.rejection_reason,
        comment=payload.comment,
    )
    sku = db.get(Sku, rec.sku_id)
    recommended_loc = db.get(StorageLocation, rec.recommended_location_id)
    current_loc = db.get(StorageLocation, rec.current_location_id) if rec.current_location_id else None
    return RecommendationOut(
        id=rec.id,
        sku_id=rec.sku_id,
        sku_code=sku.sku_code if sku else "?",
        sku_name=sku.name if sku else "?",
        inventory_record_id=rec.inventory_record_id,
        current_location_id=rec.current_location_id,
        current_location_code=current_loc.location_code if current_loc else None,
        recommended_location_id=rec.recommended_location_id,
        recommended_location_code=recommended_loc.location_code if recommended_loc else "?",
        reason=rec.reason,
        expected_benefit=rec.expected_benefit,
        distance_reduction=rec.distance_reduction,
        demand_classification=rec.demand_classification,
        confidence_score=rec.confidence_score,
        requires_approval=rec.requires_approval,
        status=rec.status,
        created_at=rec.created_at,
    )


@router.post("/{recommendation_id}/override", response_model=MovementTaskOut, status_code=status.HTTP_201_CREATED)
def override_recommendation_endpoint(
    warehouse_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    payload: OverrideRecommendationRequest,
    current_user: CurrentUser = Depends(require_permission("recommendation:approve")),
    db: Session = Depends(get_db),
) -> MovementTaskOut:

    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    rec = _get_owned_recommendation(db, warehouse_id, recommendation_id)
    movement = override_recommendation(
        db,
        rec,
        user_id=current_user.id,
        customer_id=current_user.customer_id,
        override_location_id=payload.override_location_id,
        comment=payload.comment,
    )
    return serialize_movement_task(db, movement)
