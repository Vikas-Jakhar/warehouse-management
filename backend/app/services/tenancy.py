"""Every query against a tenant-owned table must go through `scoped()` so
cross-tenant data can never leak. This is the single choke point tests target
to guarantee isolation (see tests/test_tenant_isolation.py).
"""

import uuid

from sqlalchemy.orm import Query


def scoped(query: Query, model, customer_id: uuid.UUID) -> Query:
    return query.filter(model.customer_id == customer_id)
