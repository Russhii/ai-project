"""Job tracking + execution. Default: in-process thread pool. USE_CELERY=true: Celery + Redis."""
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import AnalysisJob, Repository
from app.services.errors import NotFound
from app.services.pipeline import analyze_repository
from app.services.repository_service import refresh_repository

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="lci-job")


def create_job(db: Session, repo_id: int | None, kind: str) -> AnalysisJob:
    job = AnalysisJob(repository_id=repo_id, kind=kind, status="queued", message="Waiting for a worker")
    db.add(job)
    db.commit()
    return job


def get_job(db: Session, job_id: str) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise NotFound("Job not found")
    return job


def execute_analysis_job(job_id: str) -> None:
    """Runs in a worker thread/process with its own DB session."""
    db = SessionLocal()
    try:
        job = db.get(AnalysisJob, job_id)
        repo = db.get(Repository, job.repository_id)
        job.status, job.message = "running", "Starting"
        repo.status = "analyzing"
        db.commit()

        def progress(msg: str) -> None:
            job.message = msg
            db.commit()

        if job.kind == "refresh":
            progress("Fetching the latest repository commit")
            refresh_repository(repo)
            progress("Repository updated; starting analysis")
        job.result = analyze_repository(db, repo, progress)
        job.status, job.message = "completed", "Analysis complete"
    except Exception as exc:  # noqa: BLE001 - job boundary: record any failure
        log.exception("job %s failed", job_id)
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status, job.error, job.message = "failed", f"{type(exc).__name__}: {exc}", "Analysis failed"
        repo = db.get(Repository, job.repository_id)
        if repo:
            repo.status = "failed"
    finally:
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()


def submit_analysis(db: Session, repo: Repository) -> AnalysisJob:
    job = create_job(db, repo.id, "analyze")
    _dispatch(job)
    return job


def submit_refresh(db: Session, repo: Repository) -> AnalysisJob:
    from app.services.repository_service import validate_url
    validate_url(repo.url)
    job = create_job(db, repo.id, "refresh")
    _dispatch(job)
    return job


def _dispatch(job: AnalysisJob) -> None:
    if settings.use_celery:
        from app.worker import analyze_task
        analyze_task.delay(job.id)
    else:
        _executor.submit(execute_analysis_job, job.id)
