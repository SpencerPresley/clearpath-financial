"""Celery entry point for Reset demo. A process boundary (spec §6.1): any failure is logged and recorded on the job,
so the admin sees what happened instead of a spinner. The reset is one transaction, so a failure changes nothing."""

import logging
import time

from celery import shared_task

from demo import services
from demo.reset import reset_demo

logger = logging.getLogger(__name__)

FAILED_MESSAGE = "The reset failed and nothing changed. Try again; if it fails again, check the worker log."


@shared_task(name="demo.reset", soft_time_limit=270)
def run_demo_reset(reset_id: int) -> str:
    started = time.monotonic()
    job = services.start_reset(reset_id=reset_id)
    if job is None:
        logger.info("demo reset noop reset_id=%d (not in flight)", reset_id)
        return "noop"
    logger.info("demo reset start reset_id=%d", reset_id)
    try:
        result = reset_demo(requested_by=job.requested_by)
    except Exception:
        logger.exception("demo reset failed reset_id=%d", reset_id)
        services.fail_reset(reset_id=reset_id, error=FAILED_MESSAGE)
        outcome = "failed"
    else:
        services.finish_reset(reset_id=reset_id, result=result)
        outcome = "done"
    logger.info("demo reset %s reset_id=%d duration_ms=%d", outcome, reset_id, (time.monotonic() - started) * 1000)
    return outcome
