"""Celery entry points for the drift monitor. Process boundaries (spec §6.1): each logs start, outcome, duration, and
every failure ends as visible state on the snapshot (`failed` with a code), never a silent gap.

`run_check` is keyed by snapshot id and idempotent: it acts only if it can claim a pending snapshot. The fetch runs in
this worker process, never in a web request: a sync view fetching a page served by its own ASGI process would wait
on itself (Django runs every sync view and middleware hop on one thread per process).
"""

import asyncio
import logging
import time
from typing import Final

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded

from core.clock import SYSTEM_CLOCK, Clock
from drift import services
from drift.fetcher import FetchedPage, FetchError, fetch_page

logger = logging.getLogger(__name__)

SOFT_TIME_LIMIT: Final = 60
TIME_LIMIT: Final = 90
RETRY_COUNTDOWN: Final = 60  # seconds x attempt

clock: Clock = SYSTEM_CLOCK  # seam for tests


def fetch(url: str) -> FetchedPage:
    """The page, under the SSRF guard. A seam: tests replace it."""
    return asyncio.run(fetch_page(url))


@shared_task(
    bind=True,
    name="drift.run_check",
    max_retries=services.MAX_SCHEDULED_ATTEMPTS - 1,
    soft_time_limit=SOFT_TIME_LIMIT,
    time_limit=TIME_LIMIT,
)
def run_check(self: Task, snapshot_id: int) -> str:
    started = time.monotonic()
    claim = services.claim(snapshot_id=snapshot_id, clock=clock)
    if claim is None:
        logger.info("drift check noop snapshot_id=%d (nothing pending)", snapshot_id)
        return "noop"
    logger.info(
        "drift check start snapshot_id=%d placement_id=%d attempt=%d", snapshot_id, claim.placement_id, claim.attempt
    )
    outcome = "failed"
    retry = False
    try:
        page = fetch(claim.url)
        result = services.complete(claim=claim, page=page, clock=clock)
        outcome = f"{result.result}{' reopened' if result.reopened else ''}"
    except FetchError as error:
        if services.should_retry(claim=claim, error=error):
            services.release(claim=claim, clock=clock)
            retry, outcome = True, f"retry {error.detail}"
        else:
            services.fail(claim=claim, error=error, clock=clock)
            outcome = f"failed {error.detail}"
    except SoftTimeLimitExceeded:
        services.fail(claim=claim, code="timeout", message="The check took too long.", clock=clock)
    except Exception:
        logger.exception("drift check error snapshot_id=%d", snapshot_id)
        services.fail(claim=claim, code="error", message="The check failed unexpectedly. Try again.", clock=clock)
    logger.info(
        "drift check %s snapshot_id=%d placement_id=%d attempt=%d duration_ms=%d",
        outcome,
        snapshot_id,
        claim.placement_id,
        claim.attempt,
        (time.monotonic() - started) * 1000,
    )
    if retry:
        raise self.retry(args=(snapshot_id,), kwargs={}, countdown=RETRY_COUNTDOWN * claim.attempt)
    return outcome


@shared_task(name="drift.sweep")
def sweep() -> int:
    """Daily (beat): request a check of every monitored live placement. Returns checks requested."""
    started = time.monotonic()
    logger.info("drift sweep start")
    result = services.run_sweep(clock=clock)
    logger.info(
        "drift sweep done requested=%d skipped=%d duration_ms=%d",
        len(result.requested),
        len(result.skipped),
        (time.monotonic() - started) * 1000,
    )
    return len(result.requested)


@shared_task(name="drift.reconcile")
def reconcile() -> int:
    """Beat, every 5 minutes: stuck checks fail, lost ones are enqueued again."""
    started = time.monotonic()
    result = services.reconcile(clock=clock)
    touched = len(result.failed) + len(result.requeued)
    logger.info("drift reconcile done touched=%d duration_ms=%d", touched, (time.monotonic() - started) * 1000)
    return touched
