from app.celery_app import celery_app
from app.services.recommendation_job_runner import run_recommendation_job


@celery_app.task(name="generate_recommendations", bind=True, max_retries=0)
def generate_recommendations_task(self, job_id: str) -> None:
    run_recommendation_job(job_id)
