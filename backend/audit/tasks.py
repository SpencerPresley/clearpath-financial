"""Celery entry points for the outbox. These are process boundaries (spec §6.1): failures are logged with
context and left to Celery's retry."""

import logging
import time

from celery import shared_task

from audit.outbox import deliver, dispatch_pending, redeliver_stale

logger = logging.getLogger(__name__)


@shared_task(name="audit.dispatch_outbox")
def dispatch_outbox() -> int:
    started = time.monotonic()
    result = dispatch_pending()
    if result.events:
        logger.info(
            "outbox dispatched events=%d deliveries=%d duration_ms=%d",
            result.events,
            result.deliveries,
            (time.monotonic() - started) * 1000,
        )
    return result.events


@shared_task(
    name="audit.run_event_handler",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=8,
)
def run_event_handler(event_id: int, handler_name: str) -> str:
    started = time.monotonic()
    logger.info("event handler start event_id=%d handler=%s", event_id, handler_name)
    outcome = deliver(event_id=event_id, handler_name=handler_name)
    logger.info(
        "event handler done event_id=%d handler=%s outcome=%s duration_ms=%d",
        event_id,
        handler_name,
        outcome,
        (time.monotonic() - started) * 1000,
    )
    return outcome.value


@shared_task(name="audit.redeliver_stale_events")
def redeliver_stale_events() -> int:
    return redeliver_stale()
