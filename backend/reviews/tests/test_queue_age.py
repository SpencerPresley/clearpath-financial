"""Queue age (walkthrough S4): Age, "Waiting >3 days" and the age sorts measure from when the item last entered the
queue (submission, resubmission, new round, reopen), not from its first submission."""

from datetime import timedelta

import pytest

from accounts.models import User
from core.clock import FixedClock
from core.domain import DecisionOutcome, ItemStatus, ReopenReason
from reviews.decisions import DecisionInput, record_decision
from reviews.filters import ItemFilter, ItemSort
from reviews.models import ReviewItem
from reviews.placements import PlacementInput, record_placement
from reviews.rereview import reopen_item
from reviews.selectors import filter_items, list_items, queue_stats
from reviews.tests.conftest import Submit, approve
from reviews.tests.factories import make_item
from reviews.transitions import start_review
from reviews.versions import resubmit_item


def _waiting_ids(viewer: User, clock: FixedClock, days: int = 3) -> set[int]:
    flt = ItemFilter(waiting_more_than_days=days)
    return set(filter_items(viewer=viewer, filters=flt, clock=clock).values_list("pk", flat=True))


@pytest.mark.django_db
def test_a_reopened_item_waits_from_the_reopen_not_the_first_submission(
    submit: Submit, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    now = clock.now()
    clock.at = now - timedelta(days=40)
    item_id = submit().item_id
    approve(item_id, reviewer, clock)
    record_placement(
        actor=marketer,
        item_id=item_id,
        data=PlacementInput(location="LoanFinder", first_run=clock.today()),
        clock=clock,
    )
    clock.at = now - timedelta(minutes=1)
    reopen_item(item_id=item_id, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    clock.at = now

    item = ReviewItem.objects.get(pk=item_id)
    assert item.queue_entered_at == now - timedelta(minutes=1)
    assert item.submitted_at == now - timedelta(days=40)  # the submission itself didn't move
    row = list_items(viewer=reviewer, filters=ItemFilter(), clock=clock).rows[0]
    assert (row.queue_entered_at, row.age_days) == (now - timedelta(minutes=1), 0)
    assert item_id not in _waiting_ids(reviewer, clock)
    assert queue_stats(viewer=reviewer, clock=clock).waiting_over_3_days == 0


@pytest.mark.django_db
def test_resubmission_reenters_the_queue_and_starting_review_does_not(
    submit: Submit, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    now = clock.now()
    clock.at = now - timedelta(days=10)
    result = submit()
    item = ReviewItem.objects.get(pk=result.item_id)
    assert item.queue_entered_at == now - timedelta(days=10)

    clock.at = now - timedelta(days=9)
    start_review(item, reviewer=reviewer, at=clock.now())
    item.refresh_from_db()
    assert item.queue_entered_at == now - timedelta(days=10)  # still waiting: in review is in the queue
    record_decision(
        actor=reviewer,
        item_id=item.pk,
        data=DecisionInput(outcome=DecisionOutcome.CHANGES_REQUESTED, version_n=1, reason="Fix the rate"),
        clock=clock,
    )

    clock.at = now - timedelta(days=2)
    resubmit_item(
        actor=marketer, item_id=item.pk, content_text="Personal loans from ClearPath. Apply now.", clock=clock
    )
    clock.at = now
    item.refresh_from_db()
    assert (item.status, item.queue_entered_at) == (ItemStatus.SUBMITTED, now - timedelta(days=2))
    assert item.pk not in _waiting_ids(reviewer, clock)
    assert item.pk in _waiting_ids(reviewer, clock, days=1)


@pytest.mark.django_db
def test_age_sorts_and_queue_order_use_time_in_queue(marketer: User, reviewer: User, clock: FixedClock) -> None:
    now = clock.now()
    # Submitted long ago but back in the queue just now, vs submitted 5 days ago and waiting since.
    reopened = make_item(marketer, submitted_at=now - timedelta(days=60), queue_entered_at=now - timedelta(hours=1))
    waiting = make_item(marketer, submitted_at=now - timedelta(days=5), queue_entered_at=now - timedelta(days=5))

    def order(sort: ItemSort) -> list[int]:
        return [r.id for r in list_items(viewer=reviewer, filters=ItemFilter(), sort=sort, clock=clock).rows]

    assert order(ItemSort.OLDEST) == [waiting.pk, reopened.pk]
    assert order(ItemSort.NEWEST) == [reopened.pk, waiting.pk]
    assert order(ItemSort.QUEUE) == [waiting.pk, reopened.pk]  # same priority: longest waiting first
    assert _waiting_ids(reviewer, clock) == {waiting.pk}
