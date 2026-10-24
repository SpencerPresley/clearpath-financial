"""Placements: recorded after approval, updated, taken down; liveness and retention."""

from datetime import date, timedelta

import pytest

from accounts.models import User
from audit.models import Event
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import EventType, ItemStatus, TakedownState
from core.errors import Conflict, InvalidInput, InvalidTransition, NotPermitted
from reviews.models import Placement, ReviewItem
from reviews.placements import (
    PlacementChanges,
    PlacementInput,
    confirm_takedown,
    record_placement,
    update_placement,
)
from reviews.records import list_placements
from reviews.selectors import is_item_live
from reviews.tests.conftest import Submit


def _place(item: ReviewItem, actor: User, clock: FixedClock, **fields: object) -> int:
    data: dict[str, object] = {"location": "clearpath.com/personal-loans", "first_run": clock.today()}
    data.update(fields)
    return record_placement(actor=actor, item_id=item.pk, data=PlacementInput(**data), clock=clock)  # pyrefly: ignore[bad-argument-type]


@pytest.mark.django_db
def test_marketer_records_a_placement_of_the_approved_version(
    approved: ReviewItem, marketer: User, clock: FixedClock
) -> None:
    placement_id = _place(approved, marketer, clock, url="https://clearpath.com/pl", last_run=date(2026, 12, 31))

    placement = Placement.objects.get(pk=placement_id)
    assert (placement.approved_version, placement.created_by, placement.url) == (
        approved.current_version,
        marketer,
        "https://clearpath.com/pl",
    )
    event = Event.objects.get(type=EventType.PLACEMENT_RECORDED)
    assert event.payload == {
        "placement_id": placement_id,
        "version_id": approved.current_version_id,  # pyrefly: ignore[missing-attribute]
        "location": "clearpath.com/personal-loans",
        "first_run": "2026-10-24",
        "last_run": "2026-12-31",
    }
    assert ReviewItem.objects.get(pk=approved.pk).retention_until == date(2028, 12, 31)  # last run + 24 months


@pytest.mark.django_db
def test_placements_need_an_approved_item_and_its_owner_or_a_lead(
    submit: Submit, approved: ReviewItem, user_factory: UserFactory, lead: User, clock: FixedClock
) -> None:
    pending = ReviewItem.objects.get(pk=submit().item_id)
    other_marketer = user_factory()

    with pytest.raises(InvalidTransition):
        _place(pending, lead, clock)
    with pytest.raises(NotPermitted):
        _place(approved, other_marketer, clock)
    _place(approved, lead, clock)


@pytest.mark.django_db
def test_bad_dates_and_urls_point_at_the_field(approved: ReviewItem, marketer: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidInput) as dates:
        _place(approved, marketer, clock, last_run=clock.today() - timedelta(days=1))
    with pytest.raises(InvalidInput) as url:
        _place(approved, marketer, clock, url="javascript:alert(1)")

    assert dates.value.fields[0].loc == ("body", "last_run")
    assert url.value.fields[0].loc == ("body", "url")


@pytest.mark.django_db
def test_live_is_running_today_without_a_confirmed_takedown(
    approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock
) -> None:
    future = _place(approved, marketer, clock, first_run=clock.today() + timedelta(days=3))
    assert not is_item_live(item_id=approved.pk, today=clock.today())
    running = _place(approved, marketer, clock)
    assert is_item_live(item_id=approved.pk, today=clock.today())

    Placement.objects.filter(pk=running).update(
        takedown_state=TakedownState.REQUESTED, takedown_requested_at=clock.now()
    )
    assert is_item_live(item_id=approved.pk, today=clock.today())  # requested is still live
    confirm_takedown(actor=marketer, placement_id=running, clock=clock)

    assert not is_item_live(item_id=approved.pk, today=clock.today())
    rows = {p.id: p.is_live for p in list_placements(item_id=approved.pk, clock=clock)}
    assert rows == {future: False, running: False}


@pytest.mark.django_db
def test_update_ends_a_run_and_records_the_change(approved: ReviewItem, marketer: User, clock: FixedClock) -> None:
    placement_id = _place(approved, marketer, clock)
    assert ReviewItem.objects.get(pk=approved.pk).retention_until is None  # open-ended: still running

    update_placement(
        actor=marketer,
        placement_id=placement_id,
        changes=PlacementChanges(last_run=date(2026, 11, 30), monitored=True),
        clock=clock,
    )

    placement = Placement.objects.get(pk=placement_id)
    assert (placement.last_run, placement.monitored) == (date(2026, 11, 30), True)
    event = Event.objects.get(type=EventType.PLACEMENT_UPDATED)
    assert event.payload["changes"] == [
        {"field": "last_run", "before": None, "after": "2026-11-30"},
        {"field": "monitored", "before": False, "after": True},
    ]
    assert ReviewItem.objects.get(pk=approved.pk).retention_until == date(2028, 11, 30)


@pytest.mark.django_db
def test_update_without_changes_writes_nothing(approved: ReviewItem, marketer: User, clock: FixedClock) -> None:
    placement_id = _place(approved, marketer, clock)

    update_placement(actor=marketer, placement_id=placement_id, changes=PlacementChanges(), clock=clock)

    assert not Event.objects.filter(type=EventType.PLACEMENT_UPDATED).exists()


@pytest.mark.django_db
def test_confirm_takedown_needs_a_request(approved: ReviewItem, marketer: User, clock: FixedClock) -> None:
    placement_id = _place(approved, marketer, clock)

    with pytest.raises(Conflict):
        confirm_takedown(actor=marketer, placement_id=placement_id, clock=clock)


@pytest.mark.django_db
def test_prescreen_retention_is_three_years(approved: ReviewItem, marketer: User, clock: FixedClock) -> None:
    ReviewItem.objects.filter(pk=approved.pk).update(is_prescreen=True)
    approved.refresh_from_db()

    _place(approved, marketer, clock, last_run=date(2026, 12, 31))

    assert ReviewItem.objects.get(pk=approved.pk).retention_until == date(2029, 12, 31)


@pytest.mark.django_db
def test_confirmed_takedown_ends_the_run_for_retention(approved: ReviewItem, marketer: User, clock: FixedClock) -> None:
    placement_id = _place(approved, marketer, clock)
    Placement.objects.filter(pk=placement_id).update(
        takedown_state=TakedownState.REQUESTED, takedown_requested_at=clock.now()
    )
    clock.advance(timedelta(days=2))

    confirm_takedown(actor=marketer, placement_id=placement_id, clock=clock)

    assert ReviewItem.objects.get(pk=approved.pk).retention_until == date(2028, 10, 26)
    assert ReviewItem.objects.get(pk=approved.pk).status == ItemStatus.APPROVED
