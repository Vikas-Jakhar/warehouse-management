"""Central permission registry. Roles are seeded with these permission sets.
Later phases (recommendations, movements, uploads) reuse these same constants
so authorization stays declarative and testable.
"""

PERMISSIONS = {
    "warehouse:read",
    "warehouse:write",
    "data:upload",
    "forecast:generate",
    "recommendation:approve",
    "movement:confirm",
    "users:manage",
    "audit:read",
}

DEFAULT_ROLE_PERMISSIONS = {
    "owner": sorted(PERMISSIONS),
    "warehouse_manager": sorted(
        {
            "warehouse:read",
            "warehouse:write",
            "data:upload",
            "forecast:generate",
            "recommendation:approve",
            "movement:confirm",
            "audit:read",
        }
    ),
    "analyst": sorted({"warehouse:read", "data:upload", "forecast:generate", "audit:read"}),
    "operator": sorted({"warehouse:read", "movement:confirm"}),
    "viewer": sorted({"warehouse:read"}),
}
