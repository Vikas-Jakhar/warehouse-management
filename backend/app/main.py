import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.audit_logs import router as audit_logs_router
from app.api.v1.auth import router as auth_router
from app.api.v1.forecasts import router as forecasts_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.layout import router as layout_router
from app.api.v1.movements import router as movements_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.reports import router as reports_router
from app.api.v1.sales import router as sales_router
from app.api.v1.skus import router as skus_router
from app.api.v1.users import router as users_router
from app.api.v1.warehouses import router as warehouses_router
from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("warehouse_platform")

app = FastAPI(
    title="Intelligent Warehouse Management & Demand-Driven Inventory Optimization Platform",
    version="0.1.0",
    description="Warehouse management, forecasting, and slotting optimization platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail, "details": None}},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": 500, "message": "Internal server error", "details": None}},
    )


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "env": settings.ENV}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(warehouses_router)
app.include_router(layout_router)
app.include_router(skus_router)
app.include_router(sales_router)
app.include_router(inventory_router)
app.include_router(forecasts_router)
app.include_router(recommendations_router)
app.include_router(movements_router)
app.include_router(reports_router)
app.include_router(audit_logs_router)
