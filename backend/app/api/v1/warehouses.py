import uuid

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.warehouse import Warehouse
from app.schemas.warehouse import PaginatedWarehouses, WarehouseCreate, WarehouseOut, WarehouseUpdate
from app.services.audit import record_audit
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1/warehouses", tags=["warehouses"])


@router.get("", response_model=PaginatedWarehouses)
def list_warehouses(
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
    search: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedWarehouses:
    query = scoped(db.query(Warehouse), Warehouse, current_user.customer_id)
    if search:
        like = f"%{search}%"
        query = query.filter(Warehouse.name.ilike(like) | Warehouse.code.ilike(like))
    total = query.count()
    items = query.order_by(Warehouse.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedWarehouses(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> Warehouse:
    existing = (
        scoped(db.query(Warehouse), Warehouse, current_user.customer_id)
        .filter(Warehouse.code == payload.code)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Warehouse code already exists for this customer")

    warehouse = Warehouse(customer_id=current_user.customer_id, **payload.model_dump())
    db.add(warehouse)
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        action="create",
        after=payload.model_dump(),
    )
    db.commit()
    db.refresh(warehouse)
    return warehouse


def _get_owned_warehouse(db: Session, customer_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        # 404, not 403 — never reveal whether the resource exists for another tenant.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")
    return warehouse


@router.get("/{warehouse_id}", response_model=WarehouseOut)
def get_warehouse(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Warehouse:
    return _get_owned_warehouse(db, current_user.customer_id, warehouse_id)


@router.patch("/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(
    warehouse_id: uuid.UUID,
    payload: WarehouseUpdate,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> Warehouse:
    warehouse = _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    before = WarehouseOut.model_validate(warehouse).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(warehouse, field, value)

    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        action="update",
        before=before,
        after=updates,
    )
    db.commit()
    db.refresh(warehouse)
    return warehouse


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_warehouse(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> None:
    warehouse = _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    warehouse.is_active = False
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        action="deactivate",
    )
    db.commit()
