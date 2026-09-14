from app.celery_app import celery_app
from app.services.forecast_job_runner import run_forecast_job


@celery_app.task(name="generate_forecasts", bind=True, max_retries=0)
def generate_forecasts_task(self, job_id: str) -> None:
    run_forecast_job(job_id)
