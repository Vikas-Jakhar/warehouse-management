import uuid

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.sku import Sku
from app.schemas.sku import BulkUploadResponse, PaginatedSKUs, SKUCreate, SKUOut, SKUUpdate
from app.services.audit import record_audit
from app.services.file_parsing import parse_tabular_upload
from app.services.sku_validation import validate_sku_rows
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1/skus", tags=["skus"])


@router.get("", response_model=PaginatedSKUs)
def list_skus(
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
    search: str | None = None,
    category: str | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedSKUs:
    query = scoped(db.query(Sku), Sku, current_user.customer_id)
    if search:
        like = f"%{search}%"
        query = query.filter(Sku.name.ilike(like) | Sku.sku_code.ilike(like))
    if category:
        query = query.filter(Sku.category == category)
    total = query.count()
    items = query.order_by(Sku.sku_code).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedSKUs(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=SKUOut, status_code=status.HTTP_201_CREATED)
def create_sku(
    payload: SKUCreate,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> Sku:
    existing = (
        scoped(db.query(Sku), Sku, current_user.customer_id).filter(Sku.sku_code == payload.sku_code).one_or_none()
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "sku_code already exists for this customer")

    sku = Sku(customer_id=current_user.customer_id, **payload.model_dump())
    db.add(sku)
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="sku",
        entity_id=str(sku.id),
        action="create",
        after=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(sku)
    return sku


def _get_owned_sku(db: Session, customer_id: uuid.UUID, sku_id: uuid.UUID) -> Sku:
    sku = scoped(db.query(Sku), Sku, customer_id).filter(Sku.id == sku_id).one_or_none()
    if sku is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SKU not found")
    return sku


@router.get("/{sku_id}", response_model=SKUOut)
def get_sku(
    sku_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Sku:
    return _get_owned_sku(db, current_user.customer_id, sku_id)


@router.patch("/{sku_id}", response_model=SKUOut)
def update_sku(
    sku_id: uuid.UUID,
    payload: SKUUpdate,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> Sku:
    sku = _get_owned_sku(db, current_user.customer_id, sku_id)
    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(sku, field_name, value)
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="sku",
        entity_id=str(sku.id),
        action="update",
        after=updates,
    )
    db.commit()
    db.refresh(sku)
    return sku


@router.delete("/{sku_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_sku(
    sku_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> None:
    sku = _get_owned_sku(db, current_user.customer_id, sku_id)
    sku.is_active = False
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="sku",
        entity_id=str(sku.id),
        action="deactivate",
    )
    db.commit()


@router.post("/upload", response_model=BulkUploadResponse)
async def upload_skus(
    file: UploadFile,
    current_user: CurrentUser = Depends(require_permission("data:upload")),
    db: Session = Depends(get_db),
) -> BulkUploadResponse:
    content = await file.read()
    try:
        rows = parse_tabular_upload(file.filename or "", content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not parse file: {exc}") from exc

    existing_codes = {
        code
        for (code,) in scoped(db.query(Sku.sku_code), Sku, current_user.customer_id)
    }
    report = validate_sku_rows(rows, existing_sku_codes=existing_codes)

    if not report.is_valid:
        return BulkUploadResponse(
            **report.to_dict(), committed=False, records_created=0, error_report_csv=report.error_report_csv()
        )

    for record in report.records:
        db.add(Sku(customer_id=current_user.customer_id, **record))

    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="sku",
        entity_id="bulk",
        action="bulk_upload",
        after={"records_created": len(report.records)},
    )
    db.commit()

    return BulkUploadResponse(**report.to_dict(), committed=True, records_created=len(report.records))


@router.get("/upload/template", response_class=PlainTextResponse)
def download_sku_template(current_user: CurrentUser = Depends(get_current_user)) -> str:
    header = (
        "sku_code,name,description,category,subcategory,brand,uom,length,width,height,weight,volume,"
        "temperature_requirement,fragility,hazard_class,min_qty,max_qty,reorder_point,safety_stock,"
        "lead_time_days,shelf_life_days,requires_expiry,picking_priority,fifo_required,fefo_required,lifo_permitted\n"
    )
    sample = (
        "SKU-001,Widget A,Standard widget,Widgets,,Acme,each,10,10,5,0.5,0.5,,none,none,50,500,100,50,7,,false,3,true,false,false\n"
        "SKU-002,Frozen Berries,Perishable frozen fruit,Frozen Foods,,Acme,kg,,,,1,1,frozen,low,none,20,200,40,20,3,180,true,2,true,true,false\n"
    )
    return header + sample
