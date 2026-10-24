"""Celery entry point for export builds. A process boundary (spec §6.1): failures are logged with the job id and
recorded on the job, which the requester sees when polling."""

import logging
import time

from celery import shared_task

from exports import services

logger = logging.getLogger(__name__)


@shared_task(name="exports.run")
def run_export_task(export_id: int) -> str:
    started = time.monotonic()
    logger.info("export start export_id=%d", export_id)
    try:
        services.run_export(job_id=export_id)
    except Exception as exc:
        logger.exception("export failed export_id=%d", export_id)
        services.mark_export_failed(job_id=export_id, error=f"The export failed: {exc}. Request it again.")
        outcome = "failed"
    else:
        outcome = "done"
    logger.info("export %s export_id=%d duration_ms=%d", outcome, export_id, (time.monotonic() - started) * 1000)
    return outcome
