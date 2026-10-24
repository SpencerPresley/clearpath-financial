"""TERMS_PUBLISHED → one fan-out task per affected item, through the real outbox; and the reconcile safety net."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from accounts.models import User
from audit.models import Event
from audit.outbox import EventRecord, deliver, dispatch_pending
from checks.models import TermsRef
from core.clock import FixedClock
from core.domain import DecisionLane, EventType, ItemStatus
from reviews.models import Decision, ReviewItem
from reviews.services import SubmitItemResult
from terms import handlers, tasks
from terms.fanout import FanOutOutcome, fan_out_item
from terms.fast_track import fast_track_approve
from terms.models import OfferTerms
from terms.tests.conftest import WORKED_EXAMPLE, approve, go_live, publish

type Submit = Callable[..., SubmitItemResult]
type OnCommit = Any  # pytest-django's django_capture_on_commit_callbacks


def _approved(submit: Submit, reviewer: User, clock: FixedClock) -> int:
    item_id = submit(content_text=WORKED_EXAMPLE).item_id
    approve(item_id, reviewer, clock)
    return item_id


@pytest.mark.django_db
def test_handler_enqueues_one_task_per_affected_item_after_commit(
    pl_terms: OfferTerms,
    submit: Submit,
    reviewer: User,
    lead: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    first, second = _approved(submit, reviewer, clock), _approved(submit, reviewer, clock)
    publish(lead, clock)
    enqueued: list[int] = []
    monkeypatch.setattr(handlers, "enqueue_fan_out", enqueued.append)
    event = Event.objects.get(type=EventType.TERMS_PUBLISHED)

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        handlers.fan_out_terms_change(EventRecord.from_event(event))
        assert enqueued == []  # nothing leaves before the receipt commits
    for callback in callbacks:
        callback()

    assert enqueued == [first, second]


@pytest.mark.django_db
def test_full_path_through_the_outbox(
    pl_terms: OfferTerms,
    submit: Submit,
    marketer: User,
    reviewer: User,
    lead: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    """The worked example end to end: $10,000 / 36 months at the 7.49% floor ($311) is approved and live; the lead
    publishes a 12.99% floor through the API; the outbox fans out; the reviewer approves $337 in one click."""
    live, idle = _approved(submit, reviewer, clock), _approved(submit, reviewer, clock)
    go_live(ReviewItem.objects.get(pk=live), marketer, clock)
    publish(lead, clock)
    monkeypatch.setattr(handlers, "enqueue_fan_out", lambda item_id: tasks.fan_out_item_task(item_id, clock=clock))
    deliveries: list[tuple[int, str]] = []
    dispatch_pending(enqueue=lambda event_id, name: deliveries.append((event_id, name)))
    ours = [(e, n) for e, n in deliveries if n == "terms.fan_out"]

    with django_capture_on_commit_callbacks(execute=True):
        outcomes = [deliver(event_id=e, handler_name=n) for e, n in ours]
    with django_capture_on_commit_callbacks(execute=True):
        redelivered = [deliver(event_id=e, handler_name=n) for e, n in ours]

    assert [o.value for o in outcomes] == ["applied"]
    assert [o.value for o in redelivered] == ["duplicate"]
    statuses = dict(ReviewItem.objects.filter(pk__in=[live, idle]).values_list("pk", "status"))
    assert statuses == {live: ItemStatus.NEEDS_REREVIEW, idle: ItemStatus.EXPIRED}
    generated = ReviewItem.objects.select_related("current_version").get(pk=live).current_version
    assert generated is not None
    assert "at 12.99% APR has 36 monthly payments of $337." in generated.content_text

    result = fast_track_approve(actor=reviewer, item_id=live, version_n=generated.n, reason="Numbers only", clock=clock)

    assert (result.status, result.version_n) == (ItemStatus.APPROVED, generated.n)
    assert Decision.objects.get(pk=result.decision_id).lane == DecisionLane.FAST_TRACK


@pytest.mark.django_db
def test_reconcile_picks_up_items_a_lost_enqueue_left_behind(
    pl_terms: OfferTerms,
    submit: Submit,
    reviewer: User,
    lead: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = _approved(submit, reviewer, clock)
    publish(lead, clock)  # the handler's enqueue never happened (process died after the receipt committed)
    enqueued: list[int] = []
    monkeypatch.setattr(tasks, "enqueue_fan_out", enqueued.append)

    count = tasks.reconcile_fan_out(clock=clock)

    assert (count, enqueued) == (1, [item_id])


@pytest.mark.django_db
def test_reconcile_leaves_normal_lane_rereviews_alone(
    pl_terms: OfferTerms,
    submit: Submit,
    marketer: User,
    reviewer: User,
    lead: User,
    clock: FixedClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An item whose refs didn't fit its copy went to needs_rereview without a generated version. Its copy still
    quotes the old terms, but retrying can't help: the reconcile must not re-run it every pass."""
    item_id = _approved(submit, reviewer, clock)
    item = ReviewItem.objects.get(pk=item_id)
    go_live(item, marketer, clock)
    TermsRef.objects.filter(version=item.current_version, field="apr_max").update(quoted_value=Decimal("34.99"))
    publish(lead, clock)
    assert fan_out_item(item_id=item_id, clock=clock) is FanOutOutcome.REOPENED_NORMAL_LANE
    enqueued: list[int] = []
    monkeypatch.setattr(tasks, "enqueue_fan_out", enqueued.append)

    assert (tasks.reconcile_fan_out(clock=clock), enqueued) == (0, [])
