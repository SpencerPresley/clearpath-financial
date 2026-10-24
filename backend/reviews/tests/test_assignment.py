"""Reviewer assignment: sticky, lowest weighted load, pool; claim, manual, hand-off, bulk; and the lock."""

import threading
import time
from datetime import timedelta

import pytest
from django.db import connection, transaction

from accounts.models import User
from audit.models import Event
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import AssignmentMode, EventType, ItemStatus, RiskTier, Role
from core.errors import InvalidInput, InvalidTransition, NotPermitted
from reviews import assignment
from reviews.assignment import assign_item, auto_assign, bulk_assign, claim_item
from reviews.models import Decision, ReviewItem
from reviews.tests.conftest import Submit
from reviews.tests.factories import make_item, make_version


def _assigned(item_id: int) -> list[dict[str, object]]:
    return [e.payload for e in Event.objects.filter(item_id=item_id, type=EventType.ITEM_ASSIGNED).order_by("id")]


def _load(user: User, *tiers: RiskTier, status: ItemStatus = ItemStatus.IN_REVIEW) -> None:
    """Give `user` queued items of these tiers (owned by a throwaway marketer)."""
    owner = User.objects.filter(roles__contains=[Role.MARKETER.value]).first()
    for tier in tiers:
        make_item(owner, assignee=user, risk_tier=tier, status=status)


@pytest.fixture
def dana(user_factory: UserFactory) -> User:
    return user_factory(roles=[Role.REVIEWER], display_name="Dana")


@pytest.fixture
def sam(user_factory: UserFactory) -> User:
    return user_factory(roles=[Role.REVIEWER], display_name="Sam")


# --- automatic -------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_submit_goes_to_the_lowest_weighted_load(submit: Submit, dana: User, sam: User, clock: FixedClock) -> None:
    _load(dana, RiskTier.HIGH, RiskTier.LOW)  # 3 + 1 = 4
    _load(sam, RiskTier.MEDIUM, RiskTier.MEDIUM, RiskTier.HIGH)  # 2 + 2 + 3 = 7

    result = submit()

    item = ReviewItem.objects.get(pk=result.item_id)
    assert (item.assignee, item.assigned_at) == (dana, clock.now())
    assert _assigned(item.pk) == [
        {"assignee_id": dana.pk, "previous_assignee_id": None, "mode": "lowest_load", "reason": "Dana: load 4 vs Sam 7"}
    ]
    dana.refresh_from_db()
    assert dana.last_assigned_at == clock.now()


@pytest.mark.django_db
def test_load_counts_only_queued_items(submit: Submit, dana: User, sam: User) -> None:
    _load(dana, RiskTier.HIGH, status=ItemStatus.APPROVED)
    _load(dana, RiskTier.HIGH, status=ItemStatus.CHANGES_REQUESTED)
    _load(sam, RiskTier.LOW)

    result = submit()

    assert ReviewItem.objects.get(pk=result.item_id).assignee == dana


@pytest.mark.django_db
def test_tie_goes_to_whoever_waited_longest(submit: Submit, dana: User, sam: User, clock: FixedClock) -> None:
    User.objects.filter(pk=dana.pk).update(last_assigned_at=clock.now() - timedelta(hours=1))
    User.objects.filter(pk=sam.pk).update(last_assigned_at=clock.now() - timedelta(hours=5))

    first = submit()
    second = submit()

    assert ReviewItem.objects.get(pk=first.item_id).assignee == sam
    # Sam now carries load 1 and Dana 0.
    assert ReviewItem.objects.get(pk=second.item_id).assignee == dana


@pytest.mark.django_db
def test_unavailable_inactive_leads_and_owners_are_skipped(
    submit: Submit, user_factory: UserFactory, lead: User, marketer: User, sam: User
) -> None:
    user_factory(roles=[Role.REVIEWER], is_available=False)
    gone = user_factory(roles=[Role.REVIEWER])
    User.objects.filter(pk=gone.pk).update(is_active=False)
    _load(sam, RiskTier.HIGH, RiskTier.HIGH)
    User.objects.filter(pk=marketer.pk).update(roles=[Role.MARKETER, Role.REVIEWER])

    result = submit()

    assert ReviewItem.objects.get(pk=result.item_id).assignee == sam


@pytest.mark.django_db
def test_nobody_eligible_goes_to_the_pool(submit: Submit, lead: User) -> None:
    result = submit()

    item = ReviewItem.objects.get(pk=result.item_id)
    assert item.assignee is None
    assert _assigned(item.pk) == [
        {"assignee_id": None, "previous_assignee_id": None, "mode": "pool", "reason": "No reviewer is available"}
    ]


@pytest.mark.django_db
def test_sticky_returns_to_the_previous_reviewer(marketer: User, dana: User, sam: User, clock: FixedClock) -> None:
    _load(dana, RiskTier.HIGH, RiskTier.HIGH)
    item = make_item(marketer, assignee=sam, status=ItemStatus.SUBMITTED)
    version = make_version(item)
    Decision.objects.create(
        item=item,
        version=version,
        outcome="changes_requested",
        approver=dana,
        reason="Fix",
        ruleset_date="2026-07-21",
        decided_at=clock.now(),
    )

    with transaction.atomic():
        result = auto_assign(item=item, actor=marketer, clock=clock, sticky=True)

    assert (result.assignee_id, result.mode) == (dana.pk, AssignmentMode.STICKY)
    assert result.reason == "Back to Dana, who reviewed it before"
    assert _assigned(item.pk)[0]["previous_assignee_id"] == sam.pk


@pytest.mark.django_db
def test_sticky_falls_through_when_the_reviewer_is_away(
    marketer: User, dana: User, sam: User, clock: FixedClock
) -> None:
    item = make_item(marketer, assignee=dana, status=ItemStatus.SUBMITTED)
    User.objects.filter(pk=dana.pk).update(is_available=False)

    with transaction.atomic():
        result = auto_assign(item=item, actor=marketer, clock=clock, sticky=True)

    assert (result.assignee_id, result.mode) == (sam.pk, AssignmentMode.LOWEST_LOAD)
    assert result.reason == "Dana is unavailable. Sam: load 0"


# --- concurrency -----------------------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("locked", [True, False], ids=["with-lock", "without-lock-control"])
def test_concurrent_assignment_never_picks_from_a_stale_load(
    marketer: User, dana: User, sam: User, clock: FixedClock, monkeypatch: pytest.MonkeyPatch, locked: bool
) -> None:
    """Two real transactions. T1 assigns and holds its transaction open; T2 assigns meanwhile. With the lock, T2
    waits for T1's commit and its load query sees Dana's new item, so it picks Sam. The control run removes the
    lock and shows the race the lock exists for: T2 reads Dana's committed load of 0 and double-picks her."""
    if not locked:
        monkeypatch.setattr(assignment, "_acquire_lock", lambda: None)
    User.objects.filter(pk=dana.pk).update(last_assigned_at=clock.now() - timedelta(hours=5))
    User.objects.filter(pk=sam.pk).update(last_assigned_at=clock.now() - timedelta(hours=1))
    first = make_item(marketer)
    second = make_item(marketer)
    t1_assigned = threading.Event()
    release_t1 = threading.Event()
    picks: dict[str, int | None] = {}

    def t1() -> None:
        try:
            with transaction.atomic():
                picks["t1"] = auto_assign(item=ReviewItem.objects.get(pk=first.pk), actor=None, clock=clock).assignee_id
                t1_assigned.set()
                release_t1.wait(timeout=10)
        finally:
            connection.close()

    def t2() -> None:
        try:
            with transaction.atomic():
                picks["t2"] = auto_assign(
                    item=ReviewItem.objects.get(pk=second.pk), actor=None, clock=clock
                ).assignee_id
        finally:
            connection.close()

    thread1 = threading.Thread(target=t1)
    thread1.start()
    assert t1_assigned.wait(timeout=10)
    thread2 = threading.Thread(target=t2)
    thread2.start()
    if locked:
        _wait_for_a_blocked_advisory_lock()
        assert "t2" not in picks  # still waiting on T1
    else:
        thread2.join(timeout=10)
    release_t1.set()
    thread1.join(timeout=10)
    thread2.join(timeout=10)

    assert picks["t1"] == dana.pk
    if locked:
        assert picks["t2"] == sam.pk
        assert _assigned(second.pk)[0]["reason"] == "Sam: load 0 vs Dana 1"
    else:
        assert picks["t2"] == dana.pk


def _wait_for_a_blocked_advisory_lock() -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted")
            if cursor.fetchone()[0]:
                return
        time.sleep(0.02)
    raise AssertionError("T2 never waited on the assignment lock")


# --- claim -----------------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_claim_from_the_pool_assigns_and_starts_review(marketer: User, dana: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=ItemStatus.SUBMITTED)

    claim_item(actor=dana, item_id=item.pk, clock=clock)

    item.refresh_from_db()
    assert (item.status, item.assignee) == (ItemStatus.IN_REVIEW, dana)
    events = list(Event.objects.filter(item_id=item.pk).order_by("id").values_list("type", flat=True))
    assert events == [EventType.ITEM_ASSIGNED, EventType.ITEM_REVIEW_STARTED]
    assert _assigned(item.pk)[0]["mode"] == "claim"


@pytest.mark.django_db
def test_claiming_your_own_assignment_only_starts_review(marketer: User, dana: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=ItemStatus.SUBMITTED, assignee=dana)

    claim_item(actor=dana, item_id=item.pk, clock=clock)

    assert list(Event.objects.filter(item_id=item.pk).values_list("type", flat=True)) == [EventType.ITEM_REVIEW_STARTED]


@pytest.mark.django_db
def test_reviewer_cannot_claim_someone_elses_item_but_a_lead_can(
    marketer: User, dana: User, sam: User, lead: User, clock: FixedClock
) -> None:
    item = make_item(marketer, status=ItemStatus.SUBMITTED, assignee=dana)

    with pytest.raises(NotPermitted, match="Dana has this item"):
        claim_item(actor=sam, item_id=item.pk, clock=clock)
    claim_item(actor=lead, item_id=item.pk, clock=clock)

    assert ReviewItem.objects.get(pk=item.pk).assignee == lead
    assert _assigned(item.pk)[0]["reason"] == "Claimed from Dana"


@pytest.mark.django_db
def test_claim_needs_a_queued_item_and_a_reviewer(marketer: User, dana: User, clock: FixedClock) -> None:
    approved = make_item(marketer, status=ItemStatus.APPROVED)
    queued = make_item(marketer, status=ItemStatus.SUBMITTED)

    with pytest.raises(InvalidTransition):
        claim_item(actor=dana, item_id=approved.pk, clock=clock)
    with pytest.raises(NotPermitted):
        claim_item(actor=marketer, item_id=queued.pk, clock=clock)


@pytest.mark.django_db
def test_claim_from_needs_rereview_starts_a_full_review(marketer: User, dana: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=ItemStatus.NEEDS_REREVIEW, reopen_reason="approval_expired", assignee=dana)

    claim_item(actor=dana, item_id=item.pk, clock=clock)

    item.refresh_from_db()
    assert (item.status, item.reopen_reason) == (ItemStatus.IN_REVIEW, "approval_expired")


# --- manual, hand-off, bulk ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_lead_assigns_manually_with_a_reason(
    marketer: User, dana: User, sam: User, lead: User, clock: FixedClock
) -> None:
    item = make_item(marketer, assignee=dana)

    assign_item(actor=lead, item_id=item.pk, assignee_id=sam.pk, reason="Dana is out Friday", clock=clock)

    assert ReviewItem.objects.get(pk=item.pk).assignee == sam
    assert _assigned(item.pk) == [
        {"assignee_id": sam.pk, "previous_assignee_id": dana.pk, "mode": "manual", "reason": "Dana is out Friday"}
    ]


@pytest.mark.django_db
def test_reviewer_hands_off_only_their_own(marketer: User, dana: User, sam: User, clock: FixedClock) -> None:
    mine = make_item(marketer, assignee=dana)
    theirs = make_item(marketer, assignee=sam)

    assign_item(actor=dana, item_id=mine.pk, assignee_id=sam.pk, clock=clock)
    with pytest.raises(NotPermitted):
        assign_item(actor=dana, item_id=theirs.pk, assignee_id=dana.pk, clock=clock)

    assert _assigned(mine.pk)[0]["mode"] == "handoff"
    assert _assigned(mine.pk)[0]["reason"] == "Handed off by Dana"


@pytest.mark.django_db
def test_assignee_must_be_an_active_reviewer_other_than_the_owner(
    marketer: User, dana: User, lead: User, clock: FixedClock
) -> None:
    item = make_item(marketer)

    for bad in (marketer.pk, 999_999):
        with pytest.raises(InvalidInput) as caught:
            assign_item(actor=lead, item_id=item.pk, assignee_id=bad, clock=clock)
        assert caught.value.fields[0].loc == ("body", "assignee_id")


@pytest.mark.django_db
def test_unassign_returns_to_the_pool_and_marketers_cannot_assign(
    marketer: User, dana: User, lead: User, clock: FixedClock
) -> None:
    item = make_item(marketer, assignee=dana)

    with pytest.raises(NotPermitted):
        assign_item(actor=marketer, item_id=item.pk, assignee_id=None, clock=clock)
    assign_item(actor=lead, item_id=item.pk, assignee_id=None, clock=clock)

    assert ReviewItem.objects.get(pk=item.pk).assignee is None
    assert _assigned(item.pk)[0]["reason"] == "Returned to the pool"


@pytest.mark.django_db
def test_bulk_assign_reports_skips_per_item(marketer: User, dana: User, lead: User, clock: FixedClock) -> None:
    ok = make_item(marketer)
    approved = make_item(marketer, status=ItemStatus.APPROVED)

    result = bulk_assign(actor=lead, item_ids=[ok.pk, approved.pk, 999_999], assignee_id=dana.pk, clock=clock)

    assert result.succeeded == (ok.pk,)
    assert [(s.item_id, s.code) for s in result.skipped] == [
        (approved.pk, "invalid_transition"),
        (999_999, "not_found"),
    ]
    with pytest.raises(NotPermitted):
        bulk_assign(actor=dana, item_ids=[ok.pk], assignee_id=dana.pk, clock=clock)
