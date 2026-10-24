"""Drift checks through the real services: request, claim, complete or fail, reopen, sweep, reconcile."""

from datetime import timedelta

import pytest

from accounts.models import User
from audit.models import Event
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import (
    CheckStatus,
    DecisionLane,
    DecisionOutcome,
    DriftResult,
    DriftTrigger,
    EventType,
    ItemStatus,
    ReopenReason,
    Role,
    VersionOrigin,
)
from core.errors import Conflict, NotPermitted
from drift import services
from drift.fetcher import FetchError, FetchFailure
from drift.tests.conftest import PAGE_URL, page, page_with
from reviews.assignment import locked_item
from reviews.models import Placement, ReviewItem, Snapshot
from reviews.placements import PlacementChanges, PlacementInput, record_placement, update_placement
from reviews.rereview import send_back
from reviews.tests.conftest import CLEAN_COPY

pytestmark = pytest.mark.django_db

EDITED = CLEAN_COPY.replace("in minutes", "in seconds. Guaranteed approval")


def check(placement: Placement, clock: FixedClock, actor: User | None = None) -> services.Claim:
    snapshot_id = services.request_check(
        actor=actor,
        placement_id=placement.pk,
        trigger=DriftTrigger.SCHEDULED if actor is None else DriftTrigger.MANUAL,
        clock=clock,
    )
    claim = services.claim(snapshot_id=snapshot_id, clock=clock)
    assert claim is not None
    return claim


def item_of(placement: Placement) -> ReviewItem:
    return ReviewItem.objects.get(pk=placement.item_id)  # pyrefly: ignore[missing-attribute]


# --- requesting ------------------------------------------------------------------------------------------------


def test_request_writes_a_pending_snapshot_and_enqueues_on_commit(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int], django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        snapshot_id = services.request_check(
            actor=reviewer, placement_id=placement.pk, trigger=DriftTrigger.MANUAL, clock=clock
        )

    snapshot = Snapshot.objects.get(pk=snapshot_id)
    assert (snapshot.status, snapshot.trigger, snapshot.requested_by, snapshot.url) == (
        CheckStatus.PENDING,
        DriftTrigger.MANUAL,
        reviewer,
        PAGE_URL,
    )
    assert enqueued == [snapshot_id]
    event = Event.objects.get(type=EventType.DRIFT_CHECK_REQUESTED)
    assert (event.entity, event.entity_id, event.item_id, event.actor) == (  # pyrefly: ignore[missing-attribute]
        "placement",
        placement.pk,
        placement.item_id,
        reviewer,
    )
    assert event.payload == {"placement_id": placement.pk, "snapshot_id": snapshot_id, "trigger": "manual"}


def test_request_check_is_idempotent(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    first = services.request_check(actor=reviewer, placement_id=placement.pk, trigger=DriftTrigger.MANUAL, clock=clock)
    services.claim(snapshot_id=first, clock=clock)  # running counts as in flight too
    second = services.request_check(actor=reviewer, placement_id=placement.pk, trigger=DriftTrigger.MANUAL, clock=clock)

    assert second == first
    assert Snapshot.objects.count() == 1
    assert Event.objects.filter(type=EventType.DRIFT_CHECK_REQUESTED).count() == 1


def test_a_placement_without_a_url_cannot_be_checked(
    approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    placement_id = record_placement(
        actor=marketer, item_id=approved.pk, data=PlacementInput(location="Print", first_run=clock.today()), clock=clock
    )
    with pytest.raises(Conflict):
        services.request_check(actor=reviewer, placement_id=placement_id, trigger=DriftTrigger.MANUAL, clock=clock)


def test_who_may_check(
    placement: Placement,
    marketer: User,
    reviewer: User,
    lead: User,
    admin_user: User,
    user_factory: UserFactory,
    clock: FixedClock,
    enqueued: list[int],
) -> None:
    other_marketer = user_factory(roles=[Role.MARKETER])
    with pytest.raises(NotPermitted):
        services.request_check(
            actor=other_marketer, placement_id=placement.pk, trigger=DriftTrigger.MANUAL, clock=clock
        )

    for actor in (marketer, reviewer, lead, admin_user):  # the submitter, and any reviewer, lead, or admin
        snapshot_id = services.request_check(
            actor=actor, placement_id=placement.pk, trigger=DriftTrigger.MANUAL, clock=clock
        )
        claim = services.claim(snapshot_id=snapshot_id, clock=clock)
        assert claim is not None
        services.complete(claim=claim, page=page_with(), clock=clock)


# --- results ---------------------------------------------------------------------------------------------------


def test_unchanged_page_records_the_check_and_moves_nothing(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    claim = check(placement, clock)

    outcome = services.complete(claim=claim, page=page_with(), clock=clock)

    snapshot = Snapshot.objects.get(pk=claim.snapshot_id)
    assert outcome == services.CheckOutcome(snapshot_id=snapshot.pk, result=DriftResult.UNCHANGED, reopened=False)
    assert (snapshot.status, snapshot.result, snapshot.score, snapshot.title) == (
        CheckStatus.SUCCEEDED,
        DriftResult.UNCHANGED,
        100.0,
        "Best loans",
    )
    assert snapshot.compared_version_id == item_of(placement).current_version_id  # pyrefly: ignore[missing-attribute]
    assert "Updated today" in snapshot.text
    assert snapshot.finished_at == clock.now()
    assert len(snapshot.content_sha256) == 64
    assert item_of(placement).status == ItemStatus.APPROVED
    event = Event.objects.get(type=EventType.DRIFT_CHECKED)
    assert event.payload["status"] == "succeeded"
    assert event.payload["result"] == "unchanged"


def test_modified_page_reopens_the_live_item_to_its_approver(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    claim = check(placement, clock)

    outcome = services.complete(claim=claim, page=page_with(EDITED), clock=clock)

    item = item_of(placement)
    snapshot = Snapshot.objects.get(pk=claim.snapshot_id)
    assert outcome.reopened
    assert (item.status, item.reopen_reason, item.assignee) == (
        ItemStatus.NEEDS_REREVIEW,
        ReopenReason.DRIFT_DETECTED,
        reviewer,
    )
    assert snapshot.result == DriftResult.MODIFIED
    assert any(d["op"] == "insert" and "Guaranteed approval" in d["text"] for d in snapshot.diff), snapshot.diff
    reopened = Event.objects.get(type=EventType.ITEM_REOPENED)
    assert reopened.payload["reason"] == "drift_detected"
    assert reopened.payload["snapshot_id"] == snapshot.pk
    assert snapshot.reopen_event == reopened


def test_missing_copy_reopens_too(placement: Placement, clock: FixedClock, enqueued: list[int]) -> None:
    claim = check(placement, clock)

    services.complete(claim=claim, page=page("<p>Compare lenders. Our picks for 2026.</p>"), clock=clock)

    assert Snapshot.objects.get(pk=claim.snapshot_id).result == DriftResult.MISSING
    assert item_of(placement).reopen_reason == ReopenReason.DRIFT_DETECTED


def test_page_code_checks_are_stored_and_new_ones_marked(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    claim = check(placement, clock)

    services.complete(claim=claim, page=page_with(EDITED), clock=clock)

    findings = Snapshot.objects.get(pk=claim.snapshot_id).findings
    guaranteed = [f for f in findings if "guarantee" in (f["quote"] or "").lower()]
    assert guaranteed, findings
    assert guaranteed[0]["new"] is True
    assert set(guaranteed[0]) == {"rule_id", "citation", "severity", "message", "suggested_fix", "quote", "new"}
    event = Event.objects.get(type=EventType.DRIFT_CHECKED)
    assert event.payload["findings_count"] == len(findings)
    assert event.payload["new_findings_count"] >= 1


def test_drift_on_an_item_already_in_rereview_is_recorded_without_a_transition(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    send_back(item_id=placement.item_id, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)  # pyrefly: ignore[missing-attribute]
    claim = check(placement, clock)

    outcome = services.complete(claim=claim, page=page_with(EDITED), clock=clock)

    assert outcome == services.CheckOutcome(snapshot_id=claim.snapshot_id, result=DriftResult.MODIFIED, reopened=False)
    assert item_of(placement).reopen_reason == ReopenReason.APPROVAL_EXPIRED
    assert Event.objects.filter(type=EventType.ITEM_REOPENED).count() == 1


def test_drift_on_a_placement_that_is_not_live_moves_nothing(
    placement: Placement, marketer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    update_placement(
        actor=marketer, placement_id=placement.pk, changes=PlacementChanges(last_run=clock.today()), clock=clock
    )
    later = FixedClock(clock.now() + timedelta(days=2))
    claim = check(placement, later)

    outcome = services.complete(claim=claim, page=page_with(EDITED), clock=later)

    assert outcome.result is DriftResult.MODIFIED
    assert not outcome.reopened
    assert item_of(placement).status == ItemStatus.APPROVED


def test_compares_latest_approved_version(
    placement: Placement, lead: User, clock: FixedClock, enqueued: list[int]
) -> None:
    from django.db import transaction

    from reviews.decisions import DecisionInput, record_decision
    from reviews.versions import create_version

    # Terms change: a fast-track v2 is generated and approved; the placement still points at v1.
    v2_text = CLEAN_COPY.replace("in minutes", "in a few minutes")
    with transaction.atomic():
        item = locked_item(placement.item_id)  # pyrefly: ignore[missing-attribute]
        v1 = item.current_version
        created = create_version(
            item=item, text=v2_text, author=lead, origin=VersionOrigin.FAST_TRACK, clock=clock, based_on=v1
        )
    send_back(item_id=item.pk, reason=ReopenReason.TERMS_CHANGED, clock=clock, generated_version_id=created.version.pk)
    record_decision(
        actor=lead,
        item_id=item.pk,
        data=DecisionInput(
            outcome=DecisionOutcome.APPROVED, version_n=2, reason="Numbers updated", lane=DecisionLane.FAST_TRACK
        ),
        clock=clock,
    )
    assert Placement.objects.get(pk=placement.pk).approved_version == v1

    stale = check(placement, clock)
    services.complete(claim=stale, page=page_with(CLEAN_COPY), clock=clock)  # partner still shows v1
    stale_snapshot = Snapshot.objects.get(pk=stale.snapshot_id)

    assert stale_snapshot.compared_version == created.version
    assert stale_snapshot.result == DriftResult.MODIFIED


def test_failed_fetch_is_visible_and_moves_nothing(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    claim = check(placement, clock)
    error = FetchError(FetchFailure.HTTP_ERROR, http_status=404)

    services.fail(claim=claim, error=error, clock=clock)

    snapshot = Snapshot.objects.get(pk=claim.snapshot_id)
    assert (snapshot.status, snapshot.result, snapshot.error_code, snapshot.http_status) == (
        CheckStatus.FAILED,
        None,
        "http_error",
        404,
    )
    assert snapshot.error_message == "The site returned an error. (HTTP 404)"
    assert item_of(placement).status == ItemStatus.APPROVED
    event = Event.objects.get(type=EventType.DRIFT_CHECKED)
    assert (event.payload["status"], event.payload["error_code"], event.payload["result"]) == (
        "failed",
        "http_error",
        None,
    )


def test_a_stale_claim_cannot_finish(placement: Placement, clock: FixedClock, enqueued: list[int]) -> None:
    claim = check(placement, clock)
    services.reconcile(clock=FixedClock(clock.now() + services.STUCK_AFTER + timedelta(seconds=1)))  # fails it as stuck

    outcome = services.complete(claim=claim, page=page_with(EDITED), clock=clock)

    assert outcome.result is None
    snapshot = Snapshot.objects.get(pk=claim.snapshot_id)
    assert (snapshot.status, snapshot.error_code) == (CheckStatus.FAILED, "stuck")
    assert item_of(placement).status == ItemStatus.APPROVED


# --- retries ---------------------------------------------------------------------------------------------------


def test_scheduled_checks_retry_transient_failures_up_to_the_budget(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    timeout = FetchError(FetchFailure.TIMEOUT)
    snapshot_id = services.request_check(
        actor=None, placement_id=placement.pk, trigger=DriftTrigger.SCHEDULED, clock=clock
    )
    attempts = 0
    while True:
        claim = services.claim(snapshot_id=snapshot_id, clock=clock)
        assert claim is not None
        attempts += 1
        if not services.should_retry(claim=claim, error=timeout):
            services.fail(claim=claim, error=timeout, clock=clock)
            break
        services.release(claim=claim, clock=clock)

    assert attempts == services.MAX_SCHEDULED_ATTEMPTS
    assert Snapshot.objects.get(pk=snapshot_id).status == CheckStatus.FAILED


def test_manual_checks_and_permanent_failures_do_not_retry(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    manual = check(placement, clock, actor=reviewer)
    assert not services.should_retry(claim=manual, error=FetchError(FetchFailure.TIMEOUT))
    services.fail(claim=manual, error=FetchError(FetchFailure.TIMEOUT), clock=clock)

    scheduled = check(placement, clock)
    assert not services.should_retry(claim=scheduled, error=FetchError(FetchFailure.ADDRESS_NOT_ALLOWED))
    assert not services.should_retry(claim=scheduled, error=FetchError(FetchFailure.HTTP_ERROR, http_status=404))
    assert services.should_retry(claim=scheduled, error=FetchError(FetchFailure.HTTP_ERROR, http_status=503))


# --- sweep and reconcile ---------------------------------------------------------------------------------------


def test_sweep_requests_monitored_live_placements_of_approved_items(
    placement: Placement, submit, reviewer: User, marketer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    from reviews.tests.conftest import approve

    def another(**fields: object) -> int:
        item_id = submit().item_id
        approve(item_id, reviewer, clock)
        data = {"location": "x", "url": PAGE_URL, "first_run": clock.today(), "monitored": True} | fields
        return record_placement(actor=marketer, item_id=item_id, data=PlacementInput(**data), clock=clock)  # pyrefly: ignore[bad-argument-type]

    unmonitored = another(monitored=False)
    future = another(first_run=clock.today() + timedelta(days=5))
    no_url = another(url=None)
    rereview = another()
    send_back(item_id=Placement.objects.get(pk=rereview).item_id, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)  # pyrefly: ignore[missing-attribute]

    first = services.run_sweep(clock=clock)
    again = services.run_sweep(clock=clock)  # the first sweep's checks are still in flight

    assert set(first.requested) == {placement.pk}
    assert again.requested == ()
    assert Snapshot.objects.filter(placement_id__in=[unmonitored, future, no_url, rereview]).count() == 0
    snapshot = Snapshot.objects.get(placement=placement)
    assert (snapshot.trigger, snapshot.requested_by) == (DriftTrigger.SCHEDULED, None)


def test_reconcile_fails_stuck_checks_and_requeues_lost_ones(
    placement: Placement, approved: ReviewItem, marketer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    other = Placement.objects.get(
        pk=record_placement(
            actor=marketer,
            item_id=approved.pk,
            data=PlacementInput(location="y", url=PAGE_URL, first_run=clock.today(), monitored=True),
            clock=clock,
        )
    )
    running = check(placement, clock)
    pending = services.request_check(actor=None, placement_id=other.pk, trigger=DriftTrigger.SCHEDULED, clock=clock)
    enqueued.clear()

    soon = services.reconcile(clock=FixedClock(clock.now() + timedelta(minutes=5)))
    late = services.reconcile(clock=FixedClock(clock.now() + services.STUCK_AFTER + timedelta(seconds=1)))

    assert soon == services.ReconcileResult(failed=(), requeued=())
    assert late == services.ReconcileResult(failed=(running.snapshot_id,), requeued=(pending,))
    assert enqueued == [pending]
    assert Snapshot.objects.get(pk=running.snapshot_id).error_code == "stuck"


# --- new blocking findings beside intact copy ------------------------------------------------------------------

BESIDE = f"<p>{CLEAN_COPY}</p><p>Guaranteed approval, no credit check!</p>"


def test_new_blocking_rules_are_new_and_blocking_only() -> None:
    findings: list[dict[str, object]] = [
        {"rule_id": "a", "severity": "blocking", "new": True},
        {"rule_id": "b", "severity": "warning", "new": True},
        {"rule_id": "c", "severity": "blocking", "new": False},
        {"rule_id": "a", "severity": "blocking", "new": True},
    ]

    assert services.new_blocking_rules(findings) == frozenset({"a"})


def test_unchanged_copy_with_new_blocking_findings_flags_the_page_without_reopening(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    claim = check(placement, clock)

    outcome = services.complete(claim=claim, page=page(BESIDE), clock=clock)

    assert outcome == services.CheckOutcome(
        snapshot_id=claim.snapshot_id, result=DriftResult.UNCHANGED, reopened=False, flagged=True
    )
    assert item_of(placement).status == ItemStatus.APPROVED
    flagged = Event.objects.get(type=EventType.PAGE_FINDINGS_FLAGGED)
    assert (flagged.entity_id, flagged.item_id, flagged.actor) == (placement.pk, placement.item_id, None)  # pyrefly: ignore[missing-attribute]
    assert flagged.payload == {
        "placement_id": placement.pk,
        "snapshot_id": claim.snapshot_id,
        "rule_ids": ["claims.credit_impact", "claims.guaranteed"],
    }


def test_the_same_findings_flag_once_and_a_new_rule_flags_again(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock)
    again = services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock)
    fewer = services.complete(
        claim=check(placement, clock), page=page(f"<p>{CLEAN_COPY}</p><p>Guaranteed approval!</p>"), clock=clock
    )
    more = services.complete(
        claim=check(placement, clock),
        page=page(f"<p>{CLEAN_COPY}</p><p>Guaranteed approval! Pre-approved offers for you.</p>"),
        clock=clock,
    )

    assert (again.flagged, fewer.flagged, more.flagged) == (False, False, True)
    assert Event.objects.filter(type=EventType.PAGE_FINDINGS_FLAGGED).count() == 2


def test_a_clean_check_between_resets_the_flag(placement: Placement, clock: FixedClock, enqueued: list[int]) -> None:
    services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock)
    services.complete(claim=check(placement, clock), page=page_with(), clock=clock)

    assert services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock).flagged


def test_a_failed_check_between_does_not_reset_the_flag(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock)
    services.fail(claim=check(placement, clock), error=FetchError(FetchFailure.TIMEOUT), clock=clock)

    assert not services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock).flagged


def test_page_findings_are_not_flagged_when_nothing_is_at_risk(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    send_back(item_id=placement.item_id, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)  # pyrefly: ignore[missing-attribute]

    outcome = services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock)

    assert not outcome.flagged
    assert not Event.objects.filter(type=EventType.PAGE_FINDINGS_FLAGGED).exists()


def test_drifted_copy_reopens_instead_of_flagging(placement: Placement, clock: FixedClock, enqueued: list[int]) -> None:
    outcome = services.complete(claim=check(placement, clock), page=page_with(EDITED), clock=clock)

    assert (outcome.reopened, outcome.flagged) == (True, False)


# --- a page that can't be fetched: missing after repeated failures --------------------------------------------


def _row(
    pk: int,
    status: CheckStatus,
    error_code: str = "",
    *,
    reopened: bool = False,
    trigger: DriftTrigger = DriftTrigger.SCHEDULED,
) -> services.CheckRow:
    return services.CheckRow(id=pk, status=status, error_code=error_code, reopened=reopened, trigger=trigger)


def test_manual_failures_neither_count_nor_reset_the_streak() -> None:
    failed, manual = CheckStatus.FAILED, DriftTrigger.MANUAL

    assert services.failure_streak(
        [
            _row(5, failed, "timeout", trigger=manual),
            _row(4, failed, "http_error"),
            _row(3, failed, "http_error", trigger=manual),
            _row(2, failed, "timeout"),
            _row(1, CheckStatus.SUCCEEDED),
        ]
    ) == (4, 2)
    # A manual check that read the page is still a success: it ends the streak.
    assert services.failure_streak(
        [_row(3, failed, "http_error"), _row(2, CheckStatus.SUCCEEDED, trigger=manual), _row(1, failed, "http_error")]
    ) == (3,)


def test_failure_streak_counts_consecutive_fetch_failures_newest_first() -> None:
    failed = CheckStatus.FAILED

    assert services.failure_streak(
        [
            _row(5, failed, "http_error"),
            _row(4, failed, "timeout"),
            _row(3, CheckStatus.SUCCEEDED),
            _row(2, failed, "http_error"),
        ]
    ) == (5, 4)
    # Failures on our side say nothing about the page: they end the streak.
    for ours in ("stuck", "error", "no_approved_version"):
        rows = [_row(3, failed, "http_error"), _row(2, failed, ours), _row(1, failed, "timeout")]
        assert services.failure_streak(rows) == (3,)
    # A streak that already sent the item back is spent: the next one starts from zero.
    assert services.failure_streak(
        [_row(3, failed, "http_error"), _row(2, failed, "http_error", reopened=True), _row(1, failed, "http_error")]
    ) == (3,)
    assert services.failure_streak([]) == ()


def _fail(placement: Placement, clock: FixedClock, error: FetchError | None = None) -> services.Claim:
    claim = check(placement, clock)
    services.fail(claim=claim, error=error or FetchError(FetchFailure.HTTP_ERROR, http_status=404), clock=clock)
    return claim


def test_three_failed_fetches_in_a_row_reopen_the_live_item_as_missing(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    first = _fail(placement, clock)
    second = _fail(placement, clock, FetchError(FetchFailure.TIMEOUT))
    assert item_of(placement).status == ItemStatus.APPROVED

    third = _fail(placement, clock, FetchError(FetchFailure.HTTP_ERROR, http_status=410))

    item = item_of(placement)
    assert (item.status, item.reopen_reason, item.assignee) == (
        ItemStatus.NEEDS_REREVIEW,
        ReopenReason.DRIFT_DETECTED,
        reviewer,
    )
    snapshot = Snapshot.objects.get(pk=third.snapshot_id)
    assert (snapshot.status, snapshot.result, snapshot.error_code) == (CheckStatus.FAILED, None, "http_error")
    reopened = Event.objects.get(type=EventType.ITEM_REOPENED)
    assert snapshot.reopen_event == reopened
    assert reopened.payload == {
        "reason": "drift_detected",
        "offer_terms_id": None,
        "generated_version_id": None,
        "snapshot_id": third.snapshot_id,
        "failed_snapshot_ids": [third.snapshot_id, second.snapshot_id, first.snapshot_id],
    }


def test_a_success_resets_the_failure_streak(placement: Placement, clock: FixedClock, enqueued: list[int]) -> None:
    _fail(placement, clock)
    _fail(placement, clock)
    services.complete(claim=check(placement, clock), page=page_with(), clock=clock)
    _fail(placement, clock)
    _fail(placement, clock)

    assert item_of(placement).status == ItemStatus.APPROVED


def test_a_failure_on_our_side_ends_the_streak(placement: Placement, clock: FixedClock, enqueued: list[int]) -> None:
    _fail(placement, clock)
    _fail(placement, clock)
    services.fail(claim=check(placement, clock), code="error", message="The check failed unexpectedly.", clock=clock)
    _fail(placement, clock)
    _fail(placement, clock)

    assert item_of(placement).status == ItemStatus.APPROVED


def test_impatient_check_now_during_an_outage_cannot_reopen(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    first = _fail(placement, clock)
    second = _fail(placement, clock)
    manual = []
    for _ in range(3):
        claim = check(placement, clock, actor=reviewer)
        assert not services.fail(claim=claim, error=FetchError(FetchFailure.TIMEOUT), clock=clock)
        manual.append(claim.snapshot_id)

    # Recorded and shown, but no transition; and the scheduled streak (2) is intact.
    assert Snapshot.objects.filter(pk__in=manual, status=CheckStatus.FAILED).count() == 3
    assert item_of(placement).status == ItemStatus.APPROVED

    third = _fail(placement, clock)

    assert item_of(placement).reopen_reason == ReopenReason.DRIFT_DETECTED
    reopened = Event.objects.get(type=EventType.ITEM_REOPENED)
    assert reopened.payload["failed_snapshot_ids"] == [third.snapshot_id, second.snapshot_id, first.snapshot_id]


def test_a_page_that_stays_unreachable_reopens_once(
    placement: Placement, clock: FixedClock, enqueued: list[int]
) -> None:
    for _ in range(6):
        _fail(placement, clock)  # after the third: already in re-review, recorded with no second transition

    assert Event.objects.filter(type=EventType.ITEM_REOPENED).count() == 1


def test_failed_fetches_on_a_placement_that_is_not_live_move_nothing(
    placement: Placement, marketer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    update_placement(
        actor=marketer, placement_id=placement.pk, changes=PlacementChanges(last_run=clock.today()), clock=clock
    )
    later = FixedClock(clock.now() + timedelta(days=2))
    for _ in range(3):
        _fail(placement, later)

    assert item_of(placement).status == ItemStatus.APPROVED
    assert not Event.objects.filter(type=EventType.ITEM_REOPENED).exists()


# --- what the review screen reads ------------------------------------------------------------------------------


def test_the_read_counts_new_blocking_findings_and_the_failure_streak(
    placement: Placement, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    from drift.selectors import item_drift

    services.complete(claim=check(placement, clock), page=page(BESIDE), clock=clock)
    flagged = item_drift(item_id=placement.item_id, clock=clock).placements[0]  # pyrefly: ignore[missing-attribute]
    assert flagged.latest is not None
    assert (flagged.latest.new_blocking_count, flagged.failure_streak) == (2, 0)

    _fail(placement, clock)
    _fail(placement, clock, FetchError(FetchFailure.TIMEOUT))
    failing = item_drift(item_id=placement.item_id, clock=clock).placements[0]  # pyrefly: ignore[missing-attribute]
    assert failing.latest is not None
    assert (failing.latest.new_blocking_count, failing.failure_streak) == (0, 2)

    for _ in range(3):  # manual failures are shown as the latest check but don't move the streak
        services.fail(
            claim=check(placement, clock, actor=reviewer), error=FetchError(FetchFailure.TIMEOUT), clock=clock
        )
    clicked = item_drift(item_id=placement.item_id, clock=clock).placements[0]  # pyrefly: ignore[missing-attribute]
    assert clicked.latest is not None
    assert (clicked.latest.trigger, clicked.latest.status, clicked.failure_streak) == (
        DriftTrigger.MANUAL,
        CheckStatus.FAILED,
        2,
    )
