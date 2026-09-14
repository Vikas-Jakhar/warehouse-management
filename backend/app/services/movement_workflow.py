"""Section 16: the actual inventory location changes exactly once, at
confirmation time - never on recommendation generation, acceptance, or
movement creation. This is the single choke point that enforces that rule.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.inventory import InventoryRecord
from app.models.movement import MovementConfirmation, MovementTask
from app.models.recommendation import Recommendation
from app.models.sku import Sku
from app.models.warehouse_layout import StorageLocation
from app.schemas.movement import MovementTaskOut
from app.services.audit import record_audit


def serialize_movement_task(db: Session, movement: MovementTask) -> MovementTaskOut:
    inventory_record = db.get(InventoryRecord, movement.inventory_record_id)
    sku = db.get(Sku, inventory_record.sku_id) if inventory_record else None
    from_loc = db.get(StorageLocation, movement.from_location_id) if movement.from_location_id else None
    to_loc = db.get(StorageLocation, movement.to_location_id)
    return MovementTaskOut(
        id=movement.id,
        warehouse_id=movement.warehouse_id,
        recommendation_id=movement.recommendation_id,
        inventory_record_id=movement.inventory_record_id,
        sku_code=sku.sku_code if sku else "?",
        sku_name=sku.name if sku else "?",
        from_location_code=from_loc.location_code if from_loc else None,
        to_location_code=to_loc.location_code if to_loc else "?",
        status=movement.status,
        assigned_to=movement.assigned_to,
        created_at=movement.created_at,
    )


def start_movement(db: Session, movement: MovementTask, *, user_id: uuid.UUID, customer_id: uuid.UUID) -> MovementTask:
    if movement.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Movement task is '{movement.status}', not pending")

    movement.status = "in_progress"
    movement.assigned_to = user_id
    record_audit(
        db,
        customer_id=customer_id,
        user_id=user_id,
        entity_type="movement_task",
        entity_id=str(movement.id),
        action="start",
    )
    db.commit()
    db.refresh(movement)
    return movement


def confirm_movement(
    db: Session, movement: MovementTask, *, user_id: uuid.UUID, customer_id: uuid.UUID, notes: str | None
) -> MovementTask:
    if movement.status not in ("pending", "in_progress"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Movement task is '{movement.status}', cannot be confirmed")

    inventory_record = db.get(InventoryRecord, movement.inventory_record_id)
    if inventory_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory record for this movement no longer exists")

    before_location = inventory_record.current_location_id
    now = datetime.now(timezone.utc)

    db.add(
        MovementConfirmation(
            movement_task_id=movement.id, confirmed_by=user_id, confirmed_at=now, notes=notes
        )
    )
    movement.status = "confirmed"

    # The only line in the entire codebase that sets actual location outside
    # of upload/creation - and it only runs here, after confirmation.
    inventory_record.current_location_id = movement.to_location_id
    if inventory_record.status == "awaiting_putaway":
        inventory_record.status = "in_stock"

    if movement.recommendation_id is not None:
        recommendation = db.get(Recommendation, movement.recommendation_id)
        if recommendation is not None:
            recommendation.status = "movement_confirmed"

    record_audit(
        db,
        customer_id=customer_id,
        user_id=user_id,
        entity_type="inventory_record",
        entity_id=str(inventory_record.id),
        action="location_confirmed",
        before={"location_id": str(before_location) if before_location else None},
        after={"location_id": str(movement.to_location_id)},
    )
    db.commit()
    db.refresh(movement)
    return movement


def cancel_movement(
    db: Session, movement: MovementTask, *, user_id: uuid.UUID, customer_id: uuid.UUID, reason: str | None
) -> MovementTask:
    if movement.status not in ("pending", "in_progress"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Movement task is '{movement.status}', cannot be cancelled")

    movement.status = "cancelled"
    if movement.recommendation_id is not None:
        recommendation = db.get(Recommendation, movement.recommendation_id)
        if recommendation is not None:
            recommendation.status = "cancelled"

    record_audit(
        db,
        customer_id=customer_id,
        user_id=user_id,
        entity_type="movement_task",
        entity_id=str(movement.id),
        action="cancel",
        after={"reason": reason},
    )
    db.commit()
    db.refresh(movement)
    return movement
