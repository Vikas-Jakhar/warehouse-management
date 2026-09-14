import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.db.session import get_db
from app.models.warehouse import Warehouse
from app.models.warehouse_layout import StorageLocation, Zone
from app.schemas.layout import (
    LayoutValidationResponse,
    StorageLocationCreate,
    StorageLocationOut,
    StorageLocationUpdate,
    ZoneCreate,
    ZoneOut,
)
from app.services.audit import record_audit
from app.services.layout_validation import parse_upload, validate_layout_rows
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1/warehouses/{warehouse_id}", tags=["layout"])


def _get_owned_warehouse(db: Session, customer_id: uuid.UUID, warehouse_id: uuid.UUID) -> Warehouse:
    warehouse = (
        scoped(db.query(Warehouse), Warehouse, customer_id).filter(Warehouse.id == warehouse_id).one_or_none()
    )
    if warehouse is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Warehouse not found")
    return warehouse


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


@router.get("/zones", response_model=list[ZoneOut])
def list_zones(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Zone]:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    return db.query(Zone).filter(Zone.warehouse_id == warehouse_id).order_by(Zone.zone_code).all()


@router.post("/zones", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
def create_zone(
    warehouse_id: uuid.UUID,
    payload: ZoneCreate,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> Zone:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    existing = db.query(Zone).filter(Zone.warehouse_id == warehouse_id, Zone.zone_code == payload.zone_code).one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "zone_code already exists in this warehouse")

    zone = Zone(warehouse_id=warehouse_id, **payload.model_dump())
    db.add(zone)
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="zone",
        entity_id=str(zone.id),
        action="create",
        after=payload.model_dump(),
    )
    db.commit()
    db.refresh(zone)
    return zone


# ---------------------------------------------------------------------------
# Storage locations
# ---------------------------------------------------------------------------


@router.get("/locations", response_model=list[StorageLocationOut])
def list_locations(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StorageLocation]:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    return (
        db.query(StorageLocation)
        .filter(StorageLocation.warehouse_id == warehouse_id)
        .order_by(StorageLocation.location_code)
        .all()
    )


@router.post("/locations", response_model=StorageLocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    warehouse_id: uuid.UUID,
    payload: StorageLocationCreate,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> StorageLocation:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    existing = (
        db.query(StorageLocation)
        .filter(StorageLocation.warehouse_id == warehouse_id, StorageLocation.location_code == payload.location_code)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "location_code already exists in this warehouse")

    if payload.zone_id is not None:
        zone = db.query(Zone).filter(Zone.id == payload.zone_id, Zone.warehouse_id == warehouse_id).one_or_none()
        if zone is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "zone_id does not belong to this warehouse")

    location = StorageLocation(warehouse_id=warehouse_id, **payload.model_dump())
    db.add(location)
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="storage_location",
        entity_id=str(location.id),
        action="create",
        after=payload.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(location)
    return location


def _get_owned_location(db: Session, warehouse_id: uuid.UUID, location_id: uuid.UUID) -> StorageLocation:
    location = (
        db.query(StorageLocation)
        .filter(StorageLocation.id == location_id, StorageLocation.warehouse_id == warehouse_id)
        .one_or_none()
    )
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Storage location not found")
    return location


@router.patch("/locations/{location_id}", response_model=StorageLocationOut)
def update_location(
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    payload: StorageLocationUpdate,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> StorageLocation:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    location = _get_owned_location(db, warehouse_id, location_id)

    updates = payload.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(location, field_name, value)
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="storage_location",
        entity_id=str(location.id),
        action="update",
        after={k: str(v) for k, v in updates.items()},
    )
    db.commit()
    db.refresh(location)
    return location


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_location(
    warehouse_id: uuid.UUID,
    location_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("warehouse:write")),
    db: Session = Depends(get_db),
) -> None:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    location = _get_owned_location(db, warehouse_id, location_id)
    location.is_active = False
    location.is_available = False
    db.flush()
    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="storage_location",
        entity_id=str(location.id),
        action="deactivate",
    )
    db.commit()


# ---------------------------------------------------------------------------
# Bulk layout upload
# ---------------------------------------------------------------------------


@router.post("/layout/upload", response_model=LayoutValidationResponse)
async def upload_layout(
    warehouse_id: uuid.UUID,
    file: UploadFile,
    current_user: CurrentUser = Depends(require_permission("data:upload")),
    db: Session = Depends(get_db),
) -> LayoutValidationResponse:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)

    content = await file.read()
    try:
        rows = parse_upload(file.filename or "", content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Could not parse file: {exc}") from exc

    existing_codes = {
        code for (code,) in db.query(StorageLocation.location_code).filter(StorageLocation.warehouse_id == warehouse_id)
    }
    existing_zone_codes = {code for (code,) in db.query(Zone.zone_code).filter(Zone.warehouse_id == warehouse_id)}
    has_receiving = (
        db.query(StorageLocation)
        .filter(StorageLocation.warehouse_id == warehouse_id, StorageLocation.location_type == "receiving")
        .first()
        is not None
    )
    has_dispatch = (
        db.query(StorageLocation)
        .filter(StorageLocation.warehouse_id == warehouse_id, StorageLocation.location_type == "dispatch")
        .first()
        is not None
    )

    report = validate_layout_rows(
        rows,
        existing_location_codes=existing_codes,
        existing_zone_codes=existing_zone_codes,
        warehouse_already_has_receiving=has_receiving,
        warehouse_already_has_dispatch=has_dispatch,
    )

    if not report.is_valid:
        return LayoutValidationResponse(
            **report.to_dict(),
            committed=False,
            locations_created=0,
            zones_created=0,
            error_report_csv=report.error_report_csv(),
        )

    # All rows valid -> commit zones then locations.
    zone_id_by_code: dict[str, uuid.UUID] = {}
    for zone_code, zone_info in report.zones.items():
        zone = Zone(
            warehouse_id=warehouse_id,
            name=zone_info["name"],
            zone_code=zone_info["zone_code"],
            zone_type=zone_info["zone_type"],
        )
        db.add(zone)
        db.flush()
        zone_id_by_code[zone_code] = zone.id

    for loc in report.locations:
        zone_code = loc.pop("zone_code", None)
        zone_id = zone_id_by_code.get(zone_code) if zone_code else None
        if zone_code and zone_id is None:
            existing_zone = db.query(Zone).filter(Zone.warehouse_id == warehouse_id, Zone.zone_code == zone_code).one_or_none()
            zone_id = existing_zone.id if existing_zone else None
        db.add(StorageLocation(warehouse_id=warehouse_id, zone_id=zone_id, **loc))

    record_audit(
        db,
        customer_id=current_user.customer_id,
        user_id=current_user.id,
        entity_type="warehouse_layout",
        entity_id=str(warehouse_id),
        action="bulk_upload",
        after={"locations_created": len(report.locations), "zones_created": len(zone_id_by_code)},
    )
    db.commit()

    return LayoutValidationResponse(
        **report.to_dict(),
        committed=True,
        locations_created=len(report.locations),
        zones_created=len(zone_id_by_code),
    )


@router.get("/layout/template", response_class=PlainTextResponse)
def download_layout_template(
    warehouse_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> str:
    _get_owned_warehouse(db, current_user.customer_id, warehouse_id)
    header = (
        "location_code,location_type,storage_type,zone_code,zone_type,zone_name,"
        "aisle,rack,shelf,bin,x,y,width,height,depth,max_weight,max_volume\n"
    )
    sample = (
        "RCV-01,receiving,floor,,,,,,,,0,0,10,10,,,\n"
        "DSP-01,dispatch,floor,,,,,,,,90,0,10,10,,,\n"
        "A-01-01,storage,bin,ZONE-A,storage,Zone A Fast Movers,A,1,1,1,10,10,2,2,2,50,1\n"
    )
    return header + sample
