import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query as QueryParam
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.services.tenancy import scoped

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit-logs"])


class AuditLogOut(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: str
    action: str
    before: dict | None
    after: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAuditLogs(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int


@router.get("", response_model=PaginatedAuditLogs)
def list_audit_logs(
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
    entity_type: str | None = None,
    current_user: CurrentUser = Depends(require_permission("audit:read")),
    db: Session = Depends(get_db),
) -> PaginatedAuditLogs:
    query = scoped(db.query(AuditLog), AuditLog, current_user.customer_id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    total = query.count()
    items = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedAuditLogs(items=items, total=total, page=page, page_size=page_size)
