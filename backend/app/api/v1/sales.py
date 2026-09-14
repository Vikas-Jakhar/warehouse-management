import uuid

from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.sales import SalesRecord
from app.models.sku import Sku
from app.models.warehouse import Warehouse
from app.schemas.sales import BulkUploadResponse, PaginatedSalesRecords, SalesRecordOut
from app.services.audit import record_audit
from app.services.file_parsing import parse_tabular_upload
from app.services.sales_validation import validate_sales_rows
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1/warehouses/{warehouse_id}/sales", tags=["sales"])


def _get_owned_warehouse(db: Session, customer_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")
    return warehouse


@router.get("", response_model=PaginatedSalesRecords)
def list_sales(
    warehouse_id: uuid.UUID,
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedSalesRecords:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    query = db.query(SalesRecord).filter(SalesRecord.warehouse_id == warehouse_id)
    total = query.count()
    items = query.order_by(SalesRecord.sale_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedSalesRecords(items=items, total=total, page=page, page_size=page_size)


@router.post("/upload", response_model=BulkUploadResponse)
async def upload_sales(
    warehouse_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUser = Depends(require_permission("data:upload")),
    db: Session = Depends(get_db),
) -> BulkUploadResponse:
    warehouse = _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    content = await file.read()
    try:
        rows = parse_tabular_upload(file.filename or "", content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not parse file: {exc}") from exc

    sku_code_to_id = {
        code: sku_id for (code, sku_id) in scoped(db.query(Sku.sku_code, Sku.id), Sku, current_user.customer_id)
    }
    report = validate_sales_rows(
        rows,
        known_sku_codes=set(sku_code_to_id.keys()),
        known_warehouse_codes={warehouse.code},
    )

    if not report.is_valid:
        return BulkUploadResponse(
            **report.to_dict(), committed=False, records_created=0, error_report_csv=report.error_report_csv()
        )

    for record in report.records:
        record = dict(record)
        sku_code = record.pop("sku_code")
        record.pop("warehouse_code", None)
        db.add(SalesRecord(warehouse_id=warehouse_id, sku_id=sku_code_to_id[sku_code], **record))

    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="sales_record",
        entity_id="bulk",
        action="bulk_upload",
        after={"warehouse_id": str(warehouse_id), "records_created": len(report.records)},
    )
    db.commit()

    return BulkUploadResponse(**report.to_dict(), committed=True, records_created=len(report.records))


@router.get("/upload/template", response_class=PlainTextResponse)
def download_sales_template(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> str:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    header = (
        "date,sku_id,quantity_sold,order_id,customer_segment,sales_channel,region,"
        "promotion,price,discount,holiday_flag,returns,stockout_flag\n"
    )
    sample = (
        "2026-01-05,SKU-001,12,ORD-1001,retail,online,US-West,false,19.99,0,false,0,false\n"
        "2026-01-05,SKU-002,4,ORD-1002,wholesale,store,US-East,true,8.50,1.00,false,0,true\n"
    )
    return header + sample
