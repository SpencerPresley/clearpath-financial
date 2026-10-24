"""The re-review fan-out after an offer-terms change (product-spec Automation "New OfferTerms version"; spec §4.2
rulings 1, 2, 4).

For each approved, non-legacy item whose approved version quotes a superseded terms version:
1. generate v+1 by re-rendering the approved text under the terms in effect (`render_fast_track`): origin
   fast_track, code checks run, the AI check skipped (ruling 4);
2. live content goes to needs_rereview(terms_changed) with v+1 ready for one-click fast-track approval; content
   that isn't live goes to expired(terms_changed), and v+1 is what the marketer's next round starts from.
If the stored refs no longer fit the text (`StaleTermsRef`), no version is generated and the item takes the
normal review lane.

Items already in needs_rereview whose copy quotes superseded terms (re-review for another reason, or a second terms
change before the first was fast-tracked) get a fresh generated version from their approved text and stay where
they are: the content is live on the old numbers either way.

One item per transaction, always: `send_back` takes the assignment advisory lock after the item's row lock, so a
transaction spanning several items could deadlock against a concurrent claim or the expiry sweep (E's lock-order
contract). Idempotent: an item that was already sent back isn't approved any more, and one that was fast-tracked
quotes the terms in effect, so a redelivered event or re-run task finds nothing to do.
"""

import logging
from enum import StrEnum

from django.db import transaction

from checks.engine import StaleTermsRef, render_fast_track
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import ItemStatus, Product, ReopenReason, VersionOrigin
from reviews.assignment import locked_item
from reviews.models import Version
from reviews.rereview import send_back
from reviews.selectors import is_item_live
from reviews.versions import create_version
from terms.selectors import AFFECTED_STATUSES, affected_approvals, terms_in_effect

logger = logging.getLogger(__name__)


class FanOutOutcome(StrEnum):
    REOPENED_FAST_TRACK = "reopened_fast_track"  # live; generated version ready for one-click approval
    REOPENED_NORMAL_LANE = "reopened_normal_lane"  # live; refs didn't fit the text, no generated version
    EXPIRED = "expired"  # not live; generated version offered for the next round
    EXPIRED_NORMAL_LANE = "expired_normal_lane"  # not live; no generated version
    REGENERATED = "regenerated"  # already in needs_rereview; a fresh generated version replaces the stale copy
    REGENERATE_FAILED = "regenerate_failed"  # already in needs_rereview; refs didn't fit, left to the normal lane
    SKIPPED = "skipped"  # not (or no longer) quoting superseded terms


def fan_out_item(*, item_id: int, clock: Clock = SYSTEM_CLOCK) -> FanOutOutcome:
    """Bring one approved item's quoted terms up to date: generate v+1 and send it back (see the module docstring).

    Rendered with the terms in effect when this runs, not when the event was recorded: if a later version was
    published meanwhile, the item goes straight to its numbers. The generated version's author and the events'
    actor are the lead who published those terms.
    """
    with transaction.atomic():
        item = locked_item(item_id)  # row lock first; send_back takes the assignment lock after it
        if ItemStatus(item.status) not in AFFECTED_STATUSES or item.is_legacy:
            return FanOutOutcome.SKIPPED
        product = Product(item.product)
        found = affected_approvals(product=product, clock=clock, item_ids=[item_id])
        terms = terms_in_effect(product=product, clock=clock)
        if not found or terms is None:
            return FanOutOutcome.SKIPPED
        approval = found[0]
        lead = terms.created_by
        try:
            text = render_fast_track(approval.content_text, approval.refs, terms.typed_values)
        except StaleTermsRef:  # decide here: this item can't be fast-tracked, so it goes to the normal lane
            logger.info("fan-out item_id=%d: refs don't fit the approved text; normal lane", item_id, exc_info=True)
            generated = None
        else:
            based_on = Version.objects.get(pk=approval.version_id)
            generated = create_version(
                item=item, text=text, author=lead, origin=VersionOrigin.FAST_TRACK, based_on=based_on, clock=clock
            ).version
        if approval.status is ItemStatus.NEEDS_REREVIEW:
            return FanOutOutcome.REGENERATED if generated is not None else FanOutOutcome.REGENERATE_FAILED
        live = is_item_live(item_id=item_id, today=clock.today())
        send_back(
            item_id=item_id,
            reason=ReopenReason.TERMS_CHANGED,
            clock=clock,
            actor=lead,
            offer_terms_id=terms.pk,
            generated_version_id=generated.pk if generated is not None else None,
        )
    if live:
        return FanOutOutcome.REOPENED_FAST_TRACK if generated is not None else FanOutOutcome.REOPENED_NORMAL_LANE
    return FanOutOutcome.EXPIRED if generated is not None else FanOutOutcome.EXPIRED_NORMAL_LANE
