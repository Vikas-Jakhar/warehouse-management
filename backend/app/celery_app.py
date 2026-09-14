from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "warehouse_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=settings.CELERY_TASK_ALWAYS_EAGER,
)

# Forecasting (Phase 4) and slotting (Phase 5) tasks.
from app.tasks import forecasting_tasks  # noqa: E402,F401
from app.tasks import slotting_tasks  # noqa: E402,F401
