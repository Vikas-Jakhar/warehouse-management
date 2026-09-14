"""Section 15: accept/reject/override actions on a recommendation. Accepting
or overriding creates a MovementTask - it does NOT touch the inventory
record's actual location. That only happens on confirmed movement
(see movement_workflow.py). Rejecting never creates anything to move.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.movement import MovementTask
from app.models.recommendation import Recommendation, RecommendationDecision
from app.models.warehouse_layout import StorageLocation
from app.services.audit import record_audit


def _require_pending(recommendation: Recommendation) -> None:
    if recommendation.status != "pending_review":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Recommendation is '{recommendation.status}', not pending review - it may already have been decided.",
        )


def accept_recommendation(
    db: Session, recommendation: Recommendation, *, user_id: uuid.UUID, customer_id: uuid.UUID, comment: str | None
) -> MovementTask:
    _require_pending(recommendation)

    now = datetime.now(timezone.utc)
    db.add(
        RecommendationDecision(
            recommendation_id=recommendation.id, decision="accept", decided_by=user_id, decided_at=now, comment=comment
        )
    )
    recommendation.status = "accepted"

    movement = MovementTask(
        warehouse_id=recommendation.warehouse_id,
        recommendation_id=recommendation.id,
        inventory_record_id=recommendation.inventory_record_id,
        from_location_id=recommendation.current_location_id,
        to_location_id=recommendation.recommended_location_id,
        status="pending",
        created_by=user_id,
    )
    db.add(movement)
    db.flush()

    record_audit(
        db,
        customer_id=customer_id,
        user_id=user_id,
        entity_type="recommendation",
        entity_id=str(recommendation.id),
        action="accept",
        after={"movement_task_id": str(movement.id)},
    )
    db.commit()
    db.refresh(movement)
    return movement


def reject_recommendation(
    db: Session,
    recommendation: Recommendation,
    *,
    user_id: uuid.UUID,
    customer_id: uuid.UUID,
    rejection_reason: str,
    comment: str | None,
) -> Recommendation:
    _require_pending(recommendation)

    now = datetime.now(timezone.utc)
    db.add(
        RecommendationDecision(
            recommendation_id=recommendation.id,
            decision="reject",
            decided_by=user_id,
            decided_at=now,
            rejection_reason=rejection_reason,
            comment=comment,
        )
    )
    recommendation.status = "rejected"

    record_audit(
        db,
        customer_id=customer_id,
        user_id=user_id,
        entity_type="recommendation",
        entity_id=str(recommendation.id),
        action="reject",
        after={"rejection_reason": rejection_reason},
    )
    db.commit()
    db.refresh(recommendation)
    return recommendation


def override_recommendation(
    db: Session,
    recommendation: Recommendation,
    *,
    user_id: uuid.UUID,
    customer_id: uuid.UUID,
    override_location_id: uuid.UUID,
    comment: str | None,
) -> MovementTask:
    _require_pending(recommendation)

    override_location = (
        db.query(StorageLocation)
        .filter(StorageLocation.id == override_location_id, StorageLocation.warehouse_id == recommendation.warehouse_id)
        .one_or_none()
    )
    if override_location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Override location not found in this warehouse")
    if not override_location.is_active or override_location.is_blocked or not override_location.is_available:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Override location is not available for storage")

    now = datetime.now(timezone.utc)
    db.add(
        RecommendationDecision(
            recommendation_id=recommendation.id,
            decision="override",
            decided_by=user_id,
            decided_at=now,
            override_location_id=override_location_id,
            comment=comment,
        )
    )
    recommendation.status = "overridden"

    movement = MovementTask(
        warehouse_id=recommendation.warehouse_id,
        recommendation_id=recommendation.id,
        inventory_record_id=recommendation.inventory_record_id,
        from_location_id=recommendation.current_location_id,
        to_location_id=override_location_id,
        status="pending",
        created_by=user_id,
    )
    db.add(movement)
    db.flush()

    record_audit(
        db,
        customer_id=customer_id,
        user_id=user_id,
        entity_type="recommendation",
        entity_id=str(recommendation.id),
        action="override",
        after={"override_location_id": str(override_location_id), "movement_task_id": str(movement.id)},
    )
    db.commit()
    db.refresh(movement)
    return movement
