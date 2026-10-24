"""Celery entry points for the offer-terms fan-out. Process boundaries (spec §6.1): log start, outcome, duration."""

import logging
import time

from celery import shared_task

from core.clock import SYSTEM_CLOCK, Clock
from core.domain import ItemStatus, Product
from terms.fanout import fan_out_item
from terms.selectors import affected_approvals

logger = logging.getLogger(__name__)


@shared_task(
    name="terms.fan_out_item",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=8,
)
def fan_out_item_task(item_id: int, *, clock: Clock = SYSTEM_CLOCK) -> str:
    """One item of a terms change, in its own transaction. Idempotent, so retries and duplicates are harmless."""
    started = time.monotonic()
    logger.info("terms fan-out start item_id=%d", item_id)
    outcome = fan_out_item(item_id=item_id, clock=clock)
    logger.info(
        "terms fan-out done item_id=%d outcome=%s duration_ms=%d",
        item_id,
        outcome,
        (time.monotonic() - started) * 1000,
    )
    return outcome.value


def enqueue_fan_out(item_id: int) -> None:
    fan_out_item_task.delay(item_id)


@shared_task(name="terms.reconcile_fan_out")
def reconcile_fan_out(*, clock: Clock = SYSTEM_CLOCK) -> int:
    """Beat safety net: enqueue every *approved* item still quoting superseded terms. The handler enqueues on
    commit, so a worker dying between its receipt's commit and the enqueue would otherwise leave those items
    approved on old numbers. Nothing else leaves an approval in that state, so this is a no-op when the fan-out is
    healthy. Items already in needs_rereview are not retried here: the handler regenerates them once per publish,
    and one whose refs don't fit its copy (normal lane) would otherwise be re-run every pass, forever."""
    count = 0
    for product in (Product.PERSONAL_LOAN, Product.CREDIT_CARD):
        for affected in affected_approvals(product=product, clock=clock, statuses=(ItemStatus.APPROVED,)):
            enqueue_fan_out(affected.item_id)
            count += 1
    if count:
        logger.warning("terms fan-out reconcile enqueued %d items", count)
    return count
