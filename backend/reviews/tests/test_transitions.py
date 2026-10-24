"""The status machine table and the one function that applies it."""

import pytest
from django.db import transaction

from accounts.models import User
from audit.models import Event
from audit.payloads import ItemReopenedPayload, ItemReviewStartedPayload, ItemWithdrawnPayload
from core.clock import FixedClock
from core.domain import EventType, ItemStatus, ReopenReason
from core.errors import InvalidTransition
from reviews.models import ReviewItem
from reviews.tests.factories import make_item
from reviews.transitions import TRANSITIONS, Action, apply_transition

S = ItemStatus

# docs/plan/review-workflow.md "Transition table", verbatim.
EXPECTED = {
    Action.START_REVIEW: ({S.SUBMITTED, S.NEEDS_REREVIEW}, S.IN_REVIEW, EventType.ITEM_REVIEW_STARTED, "keep"),
    Action.APPROVE: ({S.IN_REVIEW}, S.APPROVED, EventType.DECISION_RECORDED, "clear"),
    Action.REQUEST_CHANGES: ({S.IN_REVIEW}, S.CHANGES_REQUESTED, EventType.DECISION_RECORDED, "keep"),
    Action.REJECT: ({S.IN_REVIEW}, S.REJECTED, EventType.DECISION_RECORDED, "clear"),
    Action.FAST_TRACK_APPROVE: ({S.NEEDS_REREVIEW}, S.APPROVED, EventType.DECISION_RECORDED, "clear"),
    Action.REAFFIRM: ({S.NEEDS_REREVIEW}, S.APPROVED, EventType.DECISION_RECORDED, "clear"),
    Action.RESUBMIT: ({S.CHANGES_REQUESTED}, S.SUBMITTED, EventType.ITEM_RESUBMITTED, "keep"),
    Action.REOPEN: ({S.APPROVED}, S.NEEDS_REREVIEW, EventType.ITEM_REOPENED, "set"),
    Action.EXPIRE: ({S.APPROVED}, S.EXPIRED, EventType.ITEM_EXPIRED, "set"),
    Action.PULL: ({S.NEEDS_REREVIEW}, S.WITHDRAWN, EventType.ITEM_WITHDRAWN, "clear"),
    Action.NEW_ROUND: ({S.WITHDRAWN, S.EXPIRED}, S.SUBMITTED, EventType.ITEM_NEW_ROUND_STARTED, "clear"),
}


def test_table_is_the_documented_machine() -> None:
    actual = {a: (set(t.sources), t.target, t.event, t.reopen) for a, t in TRANSITIONS.items()}

    assert actual == EXPECTED


def test_nothing_enters_draft_and_rejected_is_terminal() -> None:
    assert all(t.target is not S.DRAFT for t in TRANSITIONS.values())
    assert all(S.REJECTED not in t.sources for t in TRANSITIONS.values())


CASES = [(a, s) for a, t in TRANSITIONS.items() for s in ItemStatus if s not in t.sources]


@pytest.mark.django_db
@pytest.mark.parametrize(("action", "status"), CASES, ids=[f"{a}-from-{s}" for a, s in CASES])
def test_every_other_source_status_is_an_invalid_transition(
    marketer: User, clock: FixedClock, action: Action, status: ItemStatus
) -> None:
    item = make_item(marketer, status=status, reopen_reason=ReopenReason.TERMS_CHANGED)

    with transaction.atomic(), pytest.raises(InvalidTransition) as caught:
        apply_transition(
            item,
            action,
            actor=marketer,
            at=clock.now(),
            payload=ItemReviewStartedPayload(reviewer_id=marketer.pk),
        )

    assert caught.value.details == {"action": action.value, "from_status": status.value}
    assert ReviewItem.objects.get(pk=item.pk).status == status
    assert not Event.objects.exists()


@pytest.mark.django_db
def test_apply_records_the_event_with_from_and_to(marketer: User, reviewer: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=S.SUBMITTED)

    with transaction.atomic():
        event = apply_transition(
            item, Action.START_REVIEW, actor=reviewer, at=clock.now(), payload=ItemReviewStartedPayload(reviewer_id=1)
        )

    item.refresh_from_db()
    assert (item.status, item.updated_at) == (S.IN_REVIEW, clock.now())
    assert (event.type, event.from_status, event.to_status, event.actor) == (
        EventType.ITEM_REVIEW_STARTED,
        "submitted",
        "in_review",
        reviewer,
    )


@pytest.mark.django_db
def test_reopen_sets_and_pull_clears_the_reason(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=S.APPROVED)

    with transaction.atomic():
        apply_transition(
            item,
            Action.REOPEN,
            actor=None,
            at=clock.now(),
            payload=ItemReopenedPayload(reason=ReopenReason.APPROVAL_EXPIRED),
            reopen_reason=ReopenReason.APPROVAL_EXPIRED,
        )
    assert ReviewItem.objects.get(pk=item.pk).reopen_reason == "approval_expired"

    with transaction.atomic():
        apply_transition(
            item, Action.PULL, actor=None, at=clock.now(), payload=ItemWithdrawnPayload(reason="x", placement_ids=())
        )
    assert ReviewItem.objects.get(pk=item.pk).reopen_reason is None


@pytest.mark.django_db
def test_reopen_without_a_reason_is_a_programming_error(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=S.APPROVED)

    with transaction.atomic(), pytest.raises(ValueError, match="needs reopen_reason"):
        apply_transition(
            item,
            Action.REOPEN,
            actor=None,
            at=clock.now(),
            payload=ItemReopenedPayload(reason=ReopenReason.APPROVAL_EXPIRED),
        )
