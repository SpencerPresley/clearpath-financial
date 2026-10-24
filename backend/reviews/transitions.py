"""The item status machine: one typed table, one function that applies it (product-spec "Status machine").

`apply_transition` is the only code that changes `ReviewItem.status`. It checks the from-status against the
table, sets the status, applies the action's `reopen_reason` rule, saves, and records the action's event with
`from_status`/`to_status`, all in the caller's transaction. Anything not in the table raises
`InvalidTransition`.

`reopen_reason` drives the queue's re-review priority (Foundation's generated `queue_priority`), so it stays set
through needs_rereview -> in_review -> changes_requested -> submitted and is cleared only when the re-review
resolves (approve, fast-track, reaffirm, reject, pull) or a new round starts.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Literal

from accounts.models import User
from audit.models import Event
from audit.payloads import EventPayload, ItemReviewStartedPayload
from audit.services import record_event
from core.domain import EntityType, EventType, ItemStatus, ReopenReason
from core.errors import InvalidTransition
from reviews.models import QUEUE_STATUSES, ReviewItem

S = ItemStatus


class Action(StrEnum):
    START_REVIEW = "start_review"
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"
    FAST_TRACK_APPROVE = "fast_track_approve"
    REAFFIRM = "reaffirm"
    RESUBMIT = "resubmit"
    REOPEN = "reopen"
    EXPIRE = "expire"
    PULL = "pull"
    NEW_ROUND = "new_round"


type ReopenRule = Literal["keep", "set", "clear"]


@dataclass(frozen=True)
class Transition:
    sources: frozenset[ItemStatus]
    target: ItemStatus
    event: EventType
    reopen: ReopenRule = "keep"


def _t(sources: set[ItemStatus], target: ItemStatus, event: EventType, reopen: ReopenRule = "keep") -> Transition:
    return Transition(frozenset(sources), target, event, reopen)


TRANSITIONS: Final[dict[Action, Transition]] = {
    Action.START_REVIEW: _t({S.SUBMITTED, S.NEEDS_REREVIEW}, S.IN_REVIEW, EventType.ITEM_REVIEW_STARTED),
    Action.APPROVE: _t({S.IN_REVIEW}, S.APPROVED, EventType.DECISION_RECORDED, "clear"),
    Action.REQUEST_CHANGES: _t({S.IN_REVIEW}, S.CHANGES_REQUESTED, EventType.DECISION_RECORDED),
    Action.REJECT: _t({S.IN_REVIEW}, S.REJECTED, EventType.DECISION_RECORDED, "clear"),
    Action.FAST_TRACK_APPROVE: _t({S.NEEDS_REREVIEW}, S.APPROVED, EventType.DECISION_RECORDED, "clear"),
    Action.REAFFIRM: _t({S.NEEDS_REREVIEW}, S.APPROVED, EventType.DECISION_RECORDED, "clear"),
    Action.RESUBMIT: _t({S.CHANGES_REQUESTED}, S.SUBMITTED, EventType.ITEM_RESUBMITTED),
    Action.REOPEN: _t({S.APPROVED}, S.NEEDS_REREVIEW, EventType.ITEM_REOPENED, "set"),
    Action.EXPIRE: _t({S.APPROVED}, S.EXPIRED, EventType.ITEM_EXPIRED, "set"),
    Action.PULL: _t({S.NEEDS_REREVIEW}, S.WITHDRAWN, EventType.ITEM_WITHDRAWN, "clear"),
    Action.NEW_ROUND: _t({S.WITHDRAWN, S.EXPIRED}, S.SUBMITTED, EventType.ITEM_NEW_ROUND_STARTED, "clear"),
}


def require_transition(item: ReviewItem, action: Action) -> Transition:
    """The transition for `action` from the item's status, or InvalidTransition. For checks before any write."""
    transition = TRANSITIONS[action]
    status = ItemStatus(item.status)
    if status not in transition.sources:
        raise InvalidTransition(action=action.value, from_status=status)
    return transition


def apply_transition(  # the event's columns plus the reopen reason
    item: ReviewItem,
    action: Action,
    *,
    actor: User | None,
    at: datetime,
    payload: EventPayload,
    entity: EntityType = EntityType.ITEM,
    entity_id: int | None = None,
    reopen_reason: ReopenReason | None = None,
) -> Event:
    """Move `item` (locked by the caller) through `action`, save it, and record the action's event."""
    transition = require_transition(item, action)
    if (transition.reopen == "set") != (reopen_reason is not None):
        raise ValueError(f"{action} {'needs' if transition.reopen == 'set' else 'takes no'} reopen_reason")
    from_status = ItemStatus(item.status)
    item.status = transition.target
    if transition.reopen == "set":
        item.reopen_reason = reopen_reason
    elif transition.reopen == "clear":
        item.reopen_reason = None
    item.updated_at = at
    update_fields = ["status", "reopen_reason", "updated_at"]
    if transition.target.value in QUEUE_STATUSES and from_status.value not in QUEUE_STATUSES:
        # Resubmit, new round, reopen: the item is waiting for a reviewer again, from now (walkthrough S4).
        item.queue_entered_at = at
        update_fields.append("queue_entered_at")
    item.save(update_fields=update_fields)
    return record_event(
        type=transition.event,
        entity=entity,
        entity_id=entity_id if entity_id is not None else item.pk,
        item_id=item.pk,
        payload=payload,
        actor=actor,
        at=at,
        from_status=from_status,
        to_status=transition.target,
    )


def start_review(item: ReviewItem, *, reviewer: User, at: datetime) -> Event:
    """submitted | needs_rereview -> in_review: the "first review" marker metrics key on."""
    return apply_transition(
        item, Action.START_REVIEW, actor=reviewer, at=at, payload=ItemReviewStartedPayload(reviewer_id=reviewer.pk)
    )
