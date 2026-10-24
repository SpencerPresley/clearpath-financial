"""Outbox handler: a published terms version fans out to every approved item quoting the version it superseded."""

from functools import partial

from django.db import transaction

from audit.outbox import EventRecord, handles
from audit.payloads import TermsPublishedPayload
from core.domain import EventType
from terms.selectors import affected_approvals
from terms.tasks import enqueue_fan_out


@handles(EventType.TERMS_PUBLISHED, name="terms.fan_out")
def fan_out_terms_change(event: EventRecord) -> None:
    """Enqueue one fan-out task per affected item, after this delivery's receipt commits.

    One task per item because each item must be its own transaction (lock order; see `terms.fanout`), and this
    handler runs inside one. The work list is recomputed now as well as read from the payload: an approval that
    committed after the publish computed its list is caught here, and the tasks themselves skip anything already
    handled. On commit, not inline: an eager or fast worker must not start before the receipt is durable.
    """
    payload = event.payload
    if not isinstance(payload, TermsPublishedPayload):
        raise TypeError(f"expected TermsPublishedPayload, got {type(payload).__name__}")
    item_ids = {*payload.affected_item_ids, *(a.item_id for a in affected_approvals(product=payload.product))}
    for item_id in sorted(item_ids):
        # robust: one broker error must not drop the rest of the batch (the reconcile beat retries the one)
        transaction.on_commit(partial(enqueue_fan_out, item_id), robust=True)
