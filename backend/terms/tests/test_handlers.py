"""TERMS_PUBLISHED → one fan-out task per affected item, through the real outbox; and the reconcile safety net."""

from collections.abc import Callable
from typing import Any

import pytest

from accounts.models import User
from audit.models import Event
from audit.outbox import EventRecord, deliver, dispatch_pending
from core.clock import FixedClock
from core.domain import EventType, ItemStatus
from reviews.models import ReviewItem
from reviews.services import SubmitItemResult
from terms import handlers, tasks
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

    count = tasks.reconcile_fan_out()

    assert (count, enqueued) == (1, [item_id])
