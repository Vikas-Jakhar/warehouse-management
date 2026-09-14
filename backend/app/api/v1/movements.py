import uuid

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.movement import MovementTask
from app.models.warehouse import Warehouse
from app.schemas.movement import CancelMovementRequest, ConfirmMovementRequest, MovementTaskOut, PaginatedMovementTasks
from app.services.movement_workflow import cancel_movement, confirm_movement, serialize_movement_task, start_movement
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1/warehouses/{warehouse_id}/movements", tags=["movements"])


def _get_owned_warehouse(db: Session, customer_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")
    return warehouse


def _get_owned_movement(db: Session, warehouse_id: uuid.UUID, movement_id: uuid.UUID) -> MovementTask:
    movement = (
        db.query(MovementTask).filter(MovementTask.id == movement_id, MovementTask.warehouse_id == warehouse_id).one_or_none()
    )
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movement task not found")
    return movement


@router.get("", response_model=PaginatedMovementTasks)
def list_movements(
    warehouse_id: uuid.UUID,
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
    status_filter: str | None = QueryParam(None, alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedMovementTasks:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    query = db.query(MovementTask).filter(MovementTask.warehouse_id == warehouse_id)
    if status_filter:
        query = query.filter(MovementTask.status == status_filter)
    total = query.count()
    rows = query.order_by(MovementTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [serialize_movement_task(db, m) for m in rows]
    return PaginatedMovementTasks(items=items, total=total, page=page, page_size=page_size)


@router.post("/{movement_id}/start", response_model=MovementTaskOut)
def start_movement_endpoint(
    warehouse_id: uuid.UUID,
    movement_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("movement:confirm")),
    db: Session = Depends(get_db),
) -> MovementTaskOut:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    movement = _get_owned_movement(db, warehouse_id, movement_id)
    movement = start_movement(db, movement, user_id=current_user.id, customer_id=current_user.customer_id)
    return serialize_movement_task(db, movement)


@router.post("/{movement_id}/confirm", response_model=MovementTaskOut)
def confirm_movement_endpoint(
    warehouse_id: uuid.UUID,
    movement_id: uuid.UUID,
    payload: ConfirmMovementRequest,
    current_user: CurrentUser = Depends(require_permission("movement:confirm")),
    db: Session = Depends(get_db),
) -> MovementTaskOut:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    movement = _get_owned_movement(db, warehouse_id, movement_id)
    movement = confirm_movement(
        db, movement, user_id=current_user.id, customer_id=current_user.customer_id, notes=payload.notes
    )
    return serialize_movement_task(db, movement)


@router.post("/{movement_id}/cancel", response_model=MovementTaskOut)
def cancel_movement_endpoint(
    warehouse_id: uuid.UUID,
    movement_id: uuid.UUID,
    payload: CancelMovementRequest,
    current_user: CurrentUser = Depends(require_permission("movement:confirm")),
    db: Session = Depends(get_db),
) -> MovementTaskOut:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    movement = _get_owned_movement(db, warehouse_id, movement_id)
    movement = cancel_movement(db, movement, user_id=current_user.id, customer_id=current_user.customer_id, reason=payload.reason)
    return serialize_movement_task(db, movement)
