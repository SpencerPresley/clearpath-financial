"""One notification per action: a re-review's own sticky assignment doesn't add a second "back for your review" row
beside "needs re-review" (the re-review notice already reaches whoever the reopen assigned). A resubmission's
sticky assignment, which is its own action, still notifies."""

import pytest
from django.db import transaction

from accounts.models import User
from audit.models import Event
from audit.outbox import REGISTRY, deliver
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import EventType, NotificationKind, ReopenReason, Role
from notifications.models import Notification
from reviews.assignment import auto_assign, locked_item
from reviews.models import ReviewItem
from reviews.placements import PlacementInput, record_placement
from reviews.rereview import reopen_item


def _live(item: ReviewItem, marketer: User, clock: FixedClock) -> None:
    record_placement(
        actor=marketer,
        item_id=item.pk,
        data=PlacementInput(location="LoanFinder", first_run=clock.today()),
        clock=clock,
    )


def _notify_since(event_id: int) -> None:
    """Run every notification handler on the events after `event_id`, as the outbox would."""
    for event in Event.objects.filter(pk__gt=event_id).order_by("id"):
        for spec in REGISTRY.for_type(EventType(event.type)):
            if spec.name.startswith("notifications."):
                deliver(event_id=event.pk, handler_name=spec.name)


def _kinds(user: User) -> list[str]:
    return list(Notification.objects.filter(user=user).order_by("id").values_list("kind", flat=True))


def _last_event_id() -> int:
    return Event.objects.order_by("-id").values_list("id", flat=True).first() or 0


@pytest.mark.django_db
def test_a_reopen_tells_the_sticky_reviewer_once(
    approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    _live(approved, marketer, clock)
    before = _last_event_id()

    reopen_event_id = reopen_item(item_id=approved.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    _notify_since(before)

    assigned = Event.objects.get(pk__gt=before, type=EventType.ITEM_ASSIGNED).payload
    assert (assigned["mode"], assigned["reopen_event_id"]) == ("sticky", reopen_event_id)
    assert _kinds(reviewer) == [NotificationKind.REREVIEW]
    assert _kinds(marketer) == [NotificationKind.REREVIEW]


@pytest.mark.django_db
def test_a_reopen_that_falls_through_to_lowest_load_tells_the_new_reviewer_once(
    approved: ReviewItem, marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    _live(approved, marketer, clock)
    other = user_factory(roles=[Role.REVIEWER])
    User.objects.filter(pk=reviewer.pk).update(is_available=False)
    before = _last_event_id()

    reopen_item(item_id=approved.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    _notify_since(before)

    approved.refresh_from_db()
    assert approved.assignee == other
    assert _kinds(other) == [NotificationKind.REREVIEW]


@pytest.mark.django_db
def test_a_reopen_into_the_pool_still_tells_the_leads(
    approved: ReviewItem, marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    # The re-review notice goes to the owner and the assignee; with nobody assigned, only the pool notice reaches
    # the leads (decisions.md "Reviewer assignment" rule 3), so it stays.
    _live(approved, marketer, clock)
    lead = user_factory(roles=[Role.LEAD])
    User.objects.filter(pk=reviewer.pk).update(is_available=False)
    before = _last_event_id()

    reopen_item(item_id=approved.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    _notify_since(before)

    assert _kinds(lead) == [NotificationKind.ASSIGNMENT]
    assert _kinds(marketer) == [NotificationKind.REREVIEW]


@pytest.mark.django_db
def test_a_later_sticky_assignment_of_the_same_item_still_notifies(
    approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    # A resubmission after a re-review is its own action (versions.py), with no reopen to point at, so it still
    # says the item is back. Not keyed on the transaction: the demo seed replays whole histories in one.
    _live(approved, marketer, clock)
    reopen_item(item_id=approved.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    before = _last_event_id()

    with transaction.atomic():
        auto_assign(item=locked_item(approved.pk), actor=marketer, clock=clock, sticky=True)
    _notify_since(before)

    assert _kinds(reviewer) == [NotificationKind.ASSIGNMENT]
    assert Notification.objects.get(user=reviewer).message.endswith("is back for your review")
