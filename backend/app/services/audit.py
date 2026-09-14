import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def record_audit(
    db: Session,
    *,
    customer_id: uuid.UUID,
    user_id: uuid.UUID | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        customer_id=customer_id,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        before=before,
        after=after,
    )
    db.add(entry)
    db.flush()
    return entry
