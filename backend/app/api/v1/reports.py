import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.warehouse import Warehouse
from app.schemas.reports import CustomerOverview, WarehouseOverview
from app.services import reports
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1", tags=["reports"])


@router.get("/dashboard", response_model=CustomerOverview)
def get_customer_dashboard(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CustomerOverview:
    data = reports.customer_overview(db, current_user.customer_id)
    return CustomerOverview(**data)


@router.get("/warehouses/{warehouse_id}/reports/overview", response_model=WarehouseOverview)
def get_warehouse_overview(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WarehouseOverview:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, current_user.customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")

    data = reports.warehouse_overview(db, warehouse_id)
    return WarehouseOverview(**data)
