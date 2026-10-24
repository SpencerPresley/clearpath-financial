"""Sending approved items back: re-review of live content, expiry of content that isn't live, and the daily
sweep (product-spec "Automation"; spec §4.2 ruling 2).

`reopen_item` and `expire_item` are the only automatic writers of `approved -> *`; the sweep here and the
offer-terms fan-out (workstream F) both go through them, usually via `send_back`. Legacy items are excluded
(ruling 7): they have no versions to re-review.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from django.db import transaction

from accounts.models import User
from audit.models import Event
from audit.payloads import ApprovalExpiringPayload, ItemExpiredPayload, ItemReopenedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType, ItemStatus, ReopenReason
from core.errors import Conflict, DomainError
from reviews.assignment import auto_assign, locked_item
from reviews.models import APPROVED_OUTCOMES, Decision, ReviewItem
from reviews.selectors import is_item_live
from reviews.transitions import Action, apply_transition

logger = logging.getLogger(__name__)

EXPIRY_WARNING_DAYS: Final = 30


def _require_current(item: ReviewItem) -> None:
    if item.is_legacy:
        raise Conflict("Legacy items aren't re-reviewed or expired.", details={"item_id": item.pk})


def reopen_item(  # the event's fields
    *,
    item_id: int,
    reason: ReopenReason,
    clock: Clock = SYSTEM_CLOCK,
    actor: User | None = None,
    offer_terms_id: int | None = None,
    generated_version_id: int | None = None,
    snapshot_id: int | None = None,
    failed_snapshot_ids: Sequence[int] | None = None,
) -> int:
    """approved -> needs_rereview(reason) for live content, back to the reviewer who approved it (sticky).
    Returns the ITEM_REOPENED event id. Lock-order contract (see reviews.assignment): one item per transaction,
    because it takes the assignment lock after the item's row lock. A fan-out calls it once per item, each in its
    own transaction (optionally after locking only that same item to add its generated version). The drift monitor
    passes the `snapshot_id` of the check that found the change, and for a page that was gone on consecutive
    checks, those checks (`failed_snapshot_ids`, newest first)."""
    with transaction.atomic():
        item = locked_item(item_id)
        _require_current(item)
        event = apply_transition(
            item,
            Action.REOPEN,
            actor=actor,
            at=clock.now(),
            reopen_reason=reason,
            payload=ItemReopenedPayload(
                reason=reason,
                offer_terms_id=offer_terms_id,
                generated_version_id=generated_version_id,
                snapshot_id=snapshot_id,
                failed_snapshot_ids=list(failed_snapshot_ids) if failed_snapshot_ids is not None else None,
            ),
        )
        auto_assign(item=item, actor=actor, clock=clock, sticky=True)
    return event.pk


def expire_item(
    *,
    item_id: int,
    reason: ReopenReason,
    clock: Clock = SYSTEM_CLOCK,
    actor: User | None = None,
    offer_terms_id: int | None = None,
    generated_version_id: int | None = None,
) -> int:
    """approved -> expired(reason) for content that isn't live: nothing is at risk. The reason stays on the item
    until the marketer starts a new round. Returns the ITEM_EXPIRED event id."""
    with transaction.atomic():
        item = locked_item(item_id)
        _require_current(item)
        event = apply_transition(
            item,
            Action.EXPIRE,
            actor=actor,
            at=clock.now(),
            reopen_reason=reason,
            payload=ItemExpiredPayload(
                reason=reason, offer_terms_id=offer_terms_id, generated_version_id=generated_version_id
            ),
        )
    return event.pk


def send_back(
    *,
    item_id: int,
    reason: ReopenReason,
    clock: Clock = SYSTEM_CLOCK,
    actor: User | None = None,
    offer_terms_id: int | None = None,
    generated_version_id: int | None = None,
) -> int:
    """Live -> `reopen_item`, not live -> `expire_item` (ruling 2). The entry point for F's terms fan-out: one
    item per transaction (lock order, see `reopen_item`)."""
    action = reopen_item if is_item_live(item_id=item_id, today=clock.today()) else expire_item
    return action(
        item_id=item_id,
        reason=reason,
        clock=clock,
        actor=actor,
        offer_terms_id=offer_terms_id,
        generated_version_id=generated_version_id,
    )


# --- the daily sweep -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SweepResult:
    reopened: tuple[int, ...]
    expired: tuple[int, ...]
    warned: tuple[int, ...]
    skipped: tuple[int, ...]


def _expire_if_due(item_id: int, clock: Clock) -> bool | None:
    """Send one lapsed approval back. True: reopened (live); False: expired; None: no longer due."""
    with transaction.atomic():
        item = locked_item(item_id)
        due = item.approval_expires_at is not None and item.approval_expires_at <= clock.now()
        if item.status != ItemStatus.APPROVED or item.is_legacy or not due:
            return None
        live = is_item_live(item_id=item_id, today=clock.today())
        send_back(item_id=item_id, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)
    return live


def _latest_approval(item_id: int) -> Decision | None:
    return (
        Decision.objects.filter(item_id=item_id, outcome__in=APPROVED_OUTCOMES).order_by("-decided_at", "-pk").first()
    )


def _warn_if_due(item_id: int, clock: Clock) -> bool:
    """Record the 30-day warning for the item's current approval, once."""
    with transaction.atomic():
        item = locked_item(item_id)
        approval = _latest_approval(item_id)
        if item.status != ItemStatus.APPROVED or approval is None or item.approval_expires_at is None:
            return False
        warned = Event.objects.filter(
            item_id=item_id, type=EventType.APPROVAL_EXPIRING.value, payload__decision_id=approval.pk
        ).exists()
        if warned:
            return False
        record_event(
            type=EventType.APPROVAL_EXPIRING,
            entity=EntityType.ITEM,
            entity_id=item.pk,
            item_id=item.pk,
            payload=ApprovalExpiringPayload(decision_id=approval.pk, expires_at=item.approval_expires_at),
            actor=None,
            at=clock.now(),
        )
    return True


def run_expiry_sweep(*, clock: Clock = SYSTEM_CLOCK) -> SweepResult:
    """The daily sweep: lapsed approvals go to needs_rereview(approval_expired) if live, else expired; approvals
    lapsing within 30 days get one warning. Each item is its own transaction, so one refusal (an item that
    changed under the sweep) skips that item and the rest proceed. Running it twice changes nothing."""
    now = clock.now()
    current = ReviewItem.objects.filter(status=ItemStatus.APPROVED.value, is_legacy=False)
    due = list(current.filter(approval_expires_at__lte=now).order_by("pk").values_list("pk", flat=True))
    soon = list(
        current.filter(approval_expires_at__gt=now, approval_expires_at__lte=now + timedelta(days=EXPIRY_WARNING_DAYS))
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    reopened: list[int] = []
    expired: list[int] = []
    warned: list[int] = []
    skipped: list[int] = []
    for item_id in due:
        try:
            outcome = _expire_if_due(item_id, clock)
        except DomainError:  # decide here: this item can't move now; the next sweep retries it
            logger.warning("expiry sweep skipped item_id=%d", item_id, exc_info=True)
            skipped.append(item_id)
            continue
        if outcome is True:
            reopened.append(item_id)
        elif outcome is False:
            expired.append(item_id)
    for item_id in soon:
        try:
            if _warn_if_due(item_id, clock):
                warned.append(item_id)
        except DomainError:  # as above: skip this item, warn the rest
            logger.warning("expiry warning skipped item_id=%d", item_id, exc_info=True)
            skipped.append(item_id)
    return SweepResult(reopened=tuple(reopened), expired=tuple(expired), warned=tuple(warned), skipped=tuple(skipped))
