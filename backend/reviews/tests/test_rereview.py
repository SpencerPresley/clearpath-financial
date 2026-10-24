"""Re-review and expiry: send_back, and the daily sweep."""

from datetime import timedelta

import pytest

from accounts.models import User
from audit.models import Event
from audit.outbox import EventRecord
from core.clock import FixedClock
from core.domain import EventType, ItemStatus, ReopenReason
from core.errors import Conflict, InvalidTransition
from notifications.handlers import notify_expiry_warning
from notifications.models import Notification
from reviews.models import ReviewItem
from reviews.placements import PlacementInput, record_placement
from reviews.rereview import reopen_item, run_expiry_sweep, send_back
from reviews.tasks import expiry_sweep
from reviews.tests.factories import make_item


def _live(item: ReviewItem, marketer: User, clock: FixedClock) -> None:
    record_placement(
        actor=marketer,
        item_id=item.pk,
        data=PlacementInput(location="LoanFinder", first_run=clock.today()),
        clock=clock,
    )


@pytest.mark.django_db
def test_send_back_reopens_live_content_to_the_approver(
    approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    _live(approved, marketer, clock)

    event_id = send_back(item_id=approved.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock, offer_terms_id=7)

    approved.refresh_from_db()
    assert (approved.status, approved.reopen_reason, approved.assignee) == (
        ItemStatus.NEEDS_REREVIEW,
        "terms_changed",
        reviewer,
    )
    event = Event.objects.get(pk=event_id)
    assert (event.type, event.from_status, event.to_status, event.actor) == (
        EventType.ITEM_REOPENED,
        "approved",
        "needs_rereview",
        None,
    )
    assert event.payload == {"reason": "terms_changed", "offer_terms_id": 7, "generated_version_id": None}
    sticky = Event.objects.filter(type=EventType.ITEM_ASSIGNED, item_id=approved.pk).latest("id")
    assert sticky.payload["mode"] == "sticky"


@pytest.mark.django_db
def test_send_back_expires_content_that_isnt_live(approved: ReviewItem, clock: FixedClock) -> None:
    event_id = send_back(item_id=approved.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock)

    approved.refresh_from_db()
    assert (approved.status, approved.reopen_reason) == (ItemStatus.EXPIRED, "terms_changed")
    assert Event.objects.get(pk=event_id).type == EventType.ITEM_EXPIRED


@pytest.mark.django_db
def test_only_approved_current_items_are_sent_back(marketer: User, clock: FixedClock) -> None:
    pending = make_item(marketer, status=ItemStatus.IN_REVIEW)
    legacy = make_item(None, status=ItemStatus.APPROVED, is_legacy=True, legacy_ref="REQ-1")

    with pytest.raises(InvalidTransition):
        reopen_item(item_id=pending.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock)
    with pytest.raises(Conflict):
        send_back(item_id=legacy.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock)


@pytest.mark.django_db
def test_sweep_sends_lapsed_approvals_back_and_is_idempotent(
    approved: ReviewItem, submit: object, reviewer: User, marketer: User, clock: FixedClock
) -> None:
    from reviews.tests.conftest import approve

    live = approved
    _live(live, marketer, clock)
    idle = ReviewItem.objects.get(pk=submit().item_id)  # pyrefly: ignore[not-callable]
    approve(idle.pk, reviewer, clock)
    legacy = make_item(
        None, status=ItemStatus.APPROVED, is_legacy=True, legacy_ref="REQ-9", approval_expires_at=clock.now()
    )
    clock.advance(timedelta(days=366))

    first = run_expiry_sweep(clock=clock)
    second = run_expiry_sweep(clock=clock)

    assert (first.reopened, first.expired) == ((live.pk,), (idle.pk,))
    assert (second.reopened, second.expired, second.warned) == ((), (), ())
    assert ReviewItem.objects.get(pk=live.pk).reopen_reason == "approval_expired"
    assert ReviewItem.objects.get(pk=idle.pk).status == ItemStatus.EXPIRED
    assert ReviewItem.objects.get(pk=legacy.pk).status == ItemStatus.APPROVED


@pytest.mark.django_db
def test_sweep_warns_once_thirty_days_ahead(
    approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    clock.advance(timedelta(days=340))  # expires 2027-10-24; now 2027-09-29

    first = run_expiry_sweep(clock=clock)
    clock.advance(timedelta(days=1))
    second = run_expiry_sweep(clock=clock)

    assert (first.warned, second.warned) == ((approved.pk,), ())
    event = Event.objects.get(type=EventType.APPROVAL_EXPIRING)
    assert event.payload["expires_at"].startswith("2027-10-24")
    notify_expiry_warning(EventRecord.from_event(event))
    assert sorted(Notification.objects.values_list("user_id", "kind")) == sorted(
        [(marketer.pk, "expiry_warning"), (reviewer.pk, "expiry_warning")]
    )


@pytest.mark.django_db
def test_sweep_does_not_warn_early(approved: ReviewItem, clock: FixedClock) -> None:
    clock.advance(timedelta(days=300))

    assert run_expiry_sweep(clock=clock).warned == ()


@pytest.mark.django_db
def test_the_celery_task_runs_the_sweep(
    approved: ReviewItem, monkeypatch: pytest.MonkeyPatch, clock: FixedClock
) -> None:
    clock.advance(timedelta(days=400))
    monkeypatch.setattr("reviews.tasks.run_expiry_sweep", lambda: run_expiry_sweep(clock=clock))

    assert expiry_sweep.apply().get() == 1
    assert ReviewItem.objects.get(pk=approved.pk).status == ItemStatus.EXPIRED
