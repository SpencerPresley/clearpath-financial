"""Outbox handlers for the checks app: start the AI pre-review when a marketer's version arrives."""

from audit.outbox import EventRecord, handles
from audit.payloads import ItemNewRoundStartedPayload, ItemResubmittedPayload, ItemSubmittedPayload
from checks.prereview import request_check
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EventType
from reviews.assignment import locked_item
from reviews.models import Version

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
    happens in `checks.run_llm_prereview`, enqueued when this commits."""
    payload = event.payload
    assert isinstance(payload, ItemSubmittedPayload | ItemResubmittedPayload | ItemNewRoundStartedPayload)  # noqa: S101  # guaranteed by the registry
    version = Version.objects.get(pk=payload.version_id)
    item = locked_item(version.item_id)  # pyrefly: ignore[missing-attribute]
    request_check(item=item, version=version, actor=None, clock=clock)
