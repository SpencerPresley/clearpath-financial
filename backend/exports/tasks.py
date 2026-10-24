"""Celery entry point for export builds. A process boundary (spec §6.1): failures are logged with the job id and
recorded on the job, which the requester sees when polling.

`soft_time_limit` sits under CELERY_TASK_TIME_LIMIT (300 s) so a slow build fails visibly instead of being
killed. A worker that dies mid-build leaves the job `running`; `run_export` reclaims a running job once it is
older than the hard limit, so the redelivered message (CELERY_TASK_ACKS_LATE) finishes it.
"""

import logging
import time
from typing import Final

from celery import shared_task

from core.errors import DomainError
from exports import services

logger = logging.getLogger(__name__)

SOFT_TIME_LIMIT: Final = 270


@shared_task(name="exports.run", soft_time_limit=SOFT_TIME_LIMIT)
def run_export_task(export_id: int) -> str:
    started = time.monotonic()
    logger.info("export start export_id=%d", export_id)
    try:
        services.run_export(job_id=export_id)
    except DomainError as exc:  # e.g. the item's approval went away between request and build
        logger.warning("export refused export_id=%d: %s", export_id, exc.message)
        services.mark_export_failed(job_id=export_id, error=exc.message)
        outcome = "failed"
    except Exception:
        logger.exception("export failed export_id=%d", export_id)
        services.mark_export_failed(
            job_id=export_id,
            error=f"The export failed. Request it again; if it fails again, report export {export_id}.",
        )
        outcome = "failed"
    else:
        outcome = "done"
    logger.info("export %s export_id=%d duration_ms=%d", outcome, export_id, (time.monotonic() - started) * 1000)
    return outcome
