"""Celery entry point for the import commit. A process boundary (spec §6.1): any failure is logged with the job
id and recorded on the job, so the admin sees it instead of a spinner."""

import logging
import time

from celery import shared_task

from imports import services

logger = logging.getLogger(__name__)


@shared_task(name="imports.commit")
def commit_import_task(job_id: int) -> str:
    started = time.monotonic()
    logger.info("import commit start job_id=%d", job_id)
    try:
        services.commit_import(job_id=job_id)
    except Exception as exc:
        logger.exception("import commit failed job_id=%d", job_id)
        services.mark_import_failed(job_id=job_id, error=f"Commit failed: {exc}. Fix the mapping and commit again.")
        outcome = "failed"
    else:
        outcome = "done"
    logger.info("import commit %s job_id=%d duration_ms=%d", outcome, job_id, (time.monotonic() - started) * 1000)
    return outcome
