"""Celery entry points for the review workflow. Process boundaries (spec §6.1): log start, outcome, duration."""

import logging
import time

from celery import shared_task

from reviews.rereview import run_expiry_sweep

logger = logging.getLogger(__name__)


@shared_task(name="reviews.expiry_sweep")
def expiry_sweep() -> int:
    """Daily (beat): lapsed approvals back to re-review or expired, 30-day warnings. Returns items moved."""
    started = time.monotonic()
    logger.info("expiry sweep start")
    result = run_expiry_sweep()
    logger.info(
        "expiry sweep done reopened=%d expired=%d warned=%d skipped=%d duration_ms=%d",
        len(result.reopened),
        len(result.expired),
        len(result.warned),
        len(result.skipped),
        (time.monotonic() - started) * 1000,
    )
    return len(result.reopened) + len(result.expired)
