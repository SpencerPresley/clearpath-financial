"""Celery entry point for the import commit. A process boundary (spec §6.1): any failure is logged with the job
id and recorded on the job, so the admin sees it instead of a spinner.

`soft_time_limit` sits under CELERY_TASK_TIME_LIMIT (300 s) so a slow commit fails visibly instead of being
killed. A worker that dies mid-commit rolls the transaction back and leaves the job `committing`; with
CELERY_TASK_ACKS_LATE the message is redelivered and the commit runs again (or the admin re-POSTs commit).
"""

import logging
import time
from typing import Final

from celery import shared_task

from core.errors import DomainError
from imports import services

logger = logging.getLogger(__name__)

SOFT_TIME_LIMIT: Final = 270


@shared_task(name="imports.commit", soft_time_limit=SOFT_TIME_LIMIT)
def commit_import_task(job_id: int) -> str:
    started = time.monotonic()
    logger.info("import commit start job_id=%d", job_id)
    try:
        services.commit_import(job_id=job_id)
    except DomainError as exc:  # the sheet changed under the job (e.g. a mapping problem); the message says what
        logger.warning("import commit refused job_id=%d: %s", job_id, exc.message)
        services.mark_import_failed(job_id=job_id, error=exc.message)
        outcome = "failed"
    except Exception:
        logger.exception("import commit failed job_id=%d", job_id)
        services.mark_import_failed(
            job_id=job_id,
            error=f"The commit failed and nothing was imported. Try again; if it fails again, report import {job_id}.",
        )
        outcome = "failed"
    else:
        outcome = "done"
    logger.info("import commit %s job_id=%d duration_ms=%d", outcome, job_id, (time.monotonic() - started) * 1000)
    return outcome
