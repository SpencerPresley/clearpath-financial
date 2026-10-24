"""Outbox handlers for the checks app: start the AI pre-review when a marketer's version arrives."""

import logging

from audit.outbox import EventRecord, handles
from audit.payloads import ItemNewRoundStartedPayload, ItemResubmittedPayload, ItemSubmittedPayload
from checks.prereview import request_check
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EventType
from reviews.assignment import locked_item
from reviews.models import Version

logger = logging.getLogger(__name__)

clock: Clock = SYSTEM_CLOCK  # seam for tests


# Not VERSION_CREATED: a reviewer's edit carries its base version's AI result (E's ruling on spec §4.2 ruling 4),
# and a fast-track version skips the AI check (its diff is numeric spans that code verified).
@handles(
    EventType.ITEM_SUBMITTED,
    EventType.ITEM_RESUBMITTED,
    EventType.ITEM_NEW_ROUND_STARTED,
    name="checks.llm_prereview",
)
def start_llm_prereview(event: EventRecord) -> None:
    """Queue the AI check of the version the event created. The receipt makes this exactly-once; the model call
    happens in `checks.run_llm_prereview`, enqueued when this commits.

    A version already replaced by the time the event is delivered gets no check: its result could never reach
    the gate, and the newer version's own event requests one."""
    payload = event.payload
    assert isinstance(payload, ItemSubmittedPayload | ItemResubmittedPayload | ItemNewRoundStartedPayload)  # noqa: S101  # guaranteed by the registry
    version = Version.objects.get(pk=payload.version_id)
    item = locked_item(version.item_id)  # pyrefly: ignore[missing-attribute]
    if item.current_version_id != version.pk:  # pyrefly: ignore[missing-attribute]
        logger.info("ai check not requested event_id=%d version_id=%d (already replaced)", event.id, version.pk)
        return
    run = request_check(item=item, version=version, actor=None, clock=clock)
    logger.info("ai check requested event_id=%d version_id=%d run_id=%d", event.id, version.pk, run.pk)
