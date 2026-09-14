import uuid

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.inventory import InventoryBatch, InventoryRecord
from app.models.sku import Sku
from app.models.warehouse import Warehouse
from app.models.warehouse_layout import StorageLocation
from app.schemas.inventory import BulkUploadResponse, InventoryRecordOut, PaginatedInventoryRecords
from app.services.audit import record_audit
from app.services.file_parsing import parse_tabular_upload
from app.services.inventory_validation import validate_inventory_rows
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1/warehouses/{warehouse_id}/inventory", tags=["inventory"])


def _get_owned_warehouse(db: Session, customer_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")
    return warehouse


@router.get("", response_model=PaginatedInventoryRecords)
def list_inventory(
    warehouse_id: uuid.UUID,
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(50, ge=1, le=200),
    status_filter: str | None = QueryParam(None, alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedInventoryRecords:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    query = db.query(InventoryRecord).filter(InventoryRecord.warehouse_id == warehouse_id)
    if status_filter:
        query = query.filter(InventoryRecord.status == status_filter)
    total = query.count()
    items = query.order_by(InventoryRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    out = [
        InventoryRecordOut(
            id=r.id,
            sku_id=r.sku_id,
            batch_id=r.batch_id,
            current_location_id=r.current_location_id,
            quantity=r.quantity,
            reserved_quantity=r.reserved_quantity,
            damaged_quantity=r.damaged_quantity,
            available_quantity=r.available_quantity,
            status=r.status,
        )
        for r in items
    ]
    return PaginatedInventoryRecords(items=out, total=total, page=page, page_size=page_size)


@router.post("/upload", response_model=BulkUploadResponse)
async def upload_inventory(
    warehouse_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUser = Depends(require_permission("data:upload")),
    db: Session = Depends(get_db),
) -> BulkUploadResponse:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    content = await file.read()
    try:
        rows = parse_tabular_upload(file.filename or "", content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not parse file: {exc}") from exc

    sku_code_to_id = {
        code: sku_id for (code, sku_id) in scoped(db.query(Sku.sku_code, Sku.id), Sku, current_user.customer_id)
    }
    location_code_to_id = {
        code: loc_id
        for (code, loc_id) in db.query(StorageLocation.location_code, StorageLocation.id).filter(
            StorageLocation.warehouse_id == warehouse_id
        )
    }

    report = validate_inventory_rows(
        rows,
        known_sku_codes=set(sku_code_to_id.keys()),
        known_location_codes=set(location_code_to_id.keys()),
    )

    if not report.is_valid:
        return BulkUploadResponse(
            **report.to_dict(), committed=False, records_created=0, error_report_csv=report.error_report_csv()
        )

    for record in report.records:
        record = dict(record)
        sku_code = record.pop("sku_code")
        location_code = record.pop("location_code", None)
        batch_number = record.pop("batch_number", None)
        lot_number = record.pop("lot_number", None)
        manufacturing_date = record.pop("manufacturing_date", None)
        receiving_date = record.pop("receiving_date")
        expiry_date = record.pop("expiry_date", None)

        # Always create a batch row to carry the dates, even when the upload
        # didn't specify a batch_number - receiving_date is used by aging and
        # expiry_date by the expiring-inventory report, and both would
        # silently vanish for this record otherwise (a real gap caught by
        # comparing the aging report's output against uploaded data).
        batch = InventoryBatch(
            sku_id=sku_code_to_id[sku_code],
            batch_number=batch_number,
            lot_number=lot_number,
            manufacturing_date=manufacturing_date,
            receiving_date=receiving_date,
            expiry_date=expiry_date,
        )
        db.add(batch)
        db.flush()
        batch_id = batch.id

        db.add(
            InventoryRecord(
                warehouse_id=warehouse_id,
                sku_id=sku_code_to_id[sku_code],
                batch_id=batch_id,
                current_location_id=location_code_to_id.get(location_code) if location_code else None,
                **record,
            )
        )

    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="inventory_record",
        entity_id="bulk",
        action="bulk_upload",
        after={"warehouse_id": str(warehouse_id), "records_created": len(report.records)},
    )
    db.commit()

    return BulkUploadResponse(**report.to_dict(), committed=True, records_created=len(report.records))


@router.get("/upload/template", response_class=PlainTextResponse)
def download_inventory_template(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> str:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    header = (
        "sku_id,location_id,quantity,reserved_quantity,damaged_quantity,status,"
        "batch_number,lot_number,manufacturing_date,receiving_date,expiry_date\n"
    )
    sample = (
        "SKU-001,A-01-01,100,0,0,in_stock,BATCH-001,LOT-A,2026-01-01,2026-01-05,\n"
        "SKU-002,,50,0,0,awaiting_putaway,BATCH-002,LOT-B,2026-01-02,2026-01-06,2026-04-06\n"
    )
    return header + sample
