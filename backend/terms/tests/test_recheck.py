"""Walkthrough S20: a terms publish re-runs the code checks on in-flight items (submitted, in review, changes
requested) whose current version quotes the superseded terms, so the stale-rate finding shows up now instead of as a
409 on Approve. One item per transaction, from its own task, like the fan-out."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest

from accounts.models import User
from audit.models import Event
from audit.outbox import EventRecord
from checks.models import CheckRun, Finding
from core.clock import FixedClock
from core.domain import DecisionOutcome, EventType, FindingSource, FindingState, ItemStatus, Product
from reviews.decisions import DecisionInput, record_decision
from reviews.models import ReviewItem
from reviews.services import SubmitItemResult
from reviews.tests.conftest import RATE_COPY, ai_done, dismiss_all
from reviews.tests.factories import make_item
from reviews.transitions import start_review
from terms import handlers
from terms.fanout import RecheckOutcome, recheck_in_flight_item
from terms.models import OfferTerms
from terms.selectors import in_flight_quoting_superseded
from terms.tests.conftest import approve, publish

type Submit = Callable[..., SubmitItemResult]
type OnCommit = Any  # pytest-django's django_capture_on_commit_callbacks

pytestmark = pytest.mark.django_db


def _in_review(submit: Submit, reviewer: User, clock: FixedClock) -> ReviewItem:
    """Quotes PL v1 (7.49%-35.99%), every finding triaged: ready to approve, as CP-40 was."""
    item = ReviewItem.objects.get(pk=submit(content_text=RATE_COPY).item_id)
    start_review(item, reviewer=reviewer, at=clock.now())
    dismiss_all(item.pk, reviewer, clock)
    ai_done(item.pk)
    return ReviewItem.objects.get(pk=item.pk)


def _publish_later(lead: User, clock: FixedClock) -> None:
    """The lead publishes the new floor (7.49% -> 12.99%) an hour after the items' checks ran."""
    clock.at += timedelta(hours=1)
    publish(lead, clock)


def _open(item: ReviewItem) -> list[tuple[str, str | None]]:
    return list(
        Finding.objects.filter(version_id=item.current_version_id, state=FindingState.OPEN.value)  # pyrefly: ignore[missing-attribute]
        .order_by("pk")
        .values_list("rule_id", "quote")
    )


def test_publish_rechecks_an_in_review_item_quoting_the_old_floor(
    pl_terms: OfferTerms, submit: Submit, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _in_review(submit, reviewer, clock)
    assert _open(item) == []
    _publish_later(lead, clock)  # floor 7.49% -> 12.99%

    assert in_flight_quoting_superseded(product=Product(item.product), clock=clock) == (item.pk,)
    assert recheck_in_flight_item(item_id=item.pk, clock=clock) is RecheckOutcome.RECHECKED

    item.refresh_from_db()
    assert ("pricing.terms_available", "7.49%") in _open(item)
    assert item.open_findings_count == len(_open(item))
    assert item.status == ItemStatus.IN_REVIEW  # findings only: no state change


def test_the_recheck_is_idempotent(
    pl_terms: OfferTerms, submit: Submit, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _in_review(submit, reviewer, clock)
    _publish_later(lead, clock)
    recheck_in_flight_item(item_id=item.pk, clock=clock)
    runs = CheckRun.objects.filter(version_id=item.current_version_id, source=FindingSource.CODE).count()  # pyrefly: ignore[missing-attribute]

    assert recheck_in_flight_item(item_id=item.pk, clock=clock) is RecheckOutcome.SKIPPED
    assert CheckRun.objects.filter(version_id=item.current_version_id, source=FindingSource.CODE).count() == runs  # pyrefly: ignore[missing-attribute]


def test_changes_requested_and_submitted_items_are_rechecked_too(
    pl_terms: OfferTerms, submit: Submit, reviewer: User, lead: User, clock: FixedClock
) -> None:
    waiting = ReviewItem.objects.get(pk=submit(content_text=RATE_COPY).item_id)
    returned = _in_review(submit, reviewer, clock)
    record_decision(
        actor=reviewer,
        item_id=returned.pk,
        data=DecisionInput(outcome=DecisionOutcome.CHANGES_REQUESTED, version_n=1, reason="Add the license line"),
        clock=clock,
    )
    _publish_later(lead, clock)

    assert set(in_flight_quoting_superseded(product=Product(waiting.product), clock=clock)) == {waiting.pk, returned.pk}
    for item in (waiting, returned):
        assert recheck_in_flight_item(item_id=item.pk, clock=clock) is RecheckOutcome.RECHECKED


def test_approved_legacy_and_current_terms_items_are_left_alone(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    approved_id = submit(content_text=RATE_COPY).item_id
    approve(approved_id, reviewer, clock)  # the fan-out's, not this
    legacy = make_item(None, status=ItemStatus.SUBMITTED, is_legacy=True, legacy_ref="MCR-9", markets=[])
    _publish_later(lead, clock)
    current = _in_review(submit, reviewer, clock)  # submitted after the publish: quotes the new terms

    assert in_flight_quoting_superseded(product=Product(current.product), clock=clock) == ()
    for item_id in (approved_id, legacy.pk, current.pk):
        assert recheck_in_flight_item(item_id=item_id, clock=clock) is RecheckOutcome.SKIPPED


def test_the_publish_handler_enqueues_one_recheck_per_item_after_commit(
    pl_terms: OfferTerms,
    submit: Submit,
    reviewer: User,
    lead: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    first, second = _in_review(submit, reviewer, clock), _in_review(submit, reviewer, clock)
    _publish_later(lead, clock)
    enqueued: list[int] = []
    monkeypatch.setattr(handlers, "enqueue_recheck", enqueued.append)
    event = Event.objects.get(type=EventType.TERMS_PUBLISHED)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        handlers.recheck_in_flight(EventRecord.from_event(event))
        assert enqueued == []
    for callback in callbacks:
        callback()

    assert enqueued == [first.pk, second.pk]
