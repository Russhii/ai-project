"""Celery entry point (optional). Start with:  celery -A app.worker.celery_app worker --loglevel=info
Requires Redis and USE_CELERY=true on the API process."""
from celery import Celery

from app.config import settings
from app.db import init_db
from app.services.jobs import execute_analysis_job

celery_app = Celery("lci", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_acks_late = True
init_db()


@celery_app.task(name="lci.analyze", autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=3)
def analyze_task(job_id: str) -> None:
    execute_analysis_job(job_id)
