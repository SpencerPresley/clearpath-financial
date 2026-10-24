"""The event log as transactional outbox: at-least-once delivery, exactly-once effects."""

import threading
from datetime import timedelta

import pytest
from django.db import connection, transaction

from accounts.models import User
from audit.models import Event, OutboxCursor, ProcessedEvent
from audit.outbox import (
    CURSOR_NAME,
    Delivery,
    EventRecord,
    HandlerRegistry,
    deliver,
    dispatch_pending,
    redeliver_stale,
)
from audit.payloads import ItemAssignedPayload, UserAvailabilityChangedPayload
from audit.services import record_event
from core.clock import FixedClock
from core.domain import AssignmentMode, EntityType, EventType


class Recorder:
    """Enqueue stand-in: remembers what the dispatcher asked to deliver."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def __call__(self, event_id: int, handler_name: str) -> None:
        self.calls.append((event_id, handler_name))


def _availability_event(user: User, clock: FixedClock, *, available: bool = False) -> Event:
    with transaction.atomic():
        return record_event(
            type=EventType.USER_AVAILABILITY_CHANGED,
            entity=EntityType.USER,
            entity_id=user.pk,
            payload=UserAvailabilityChangedPayload(user_id=user.pk, is_available=available),
            actor=user,
            at=clock.now(),
        )


def _registry() -> tuple[HandlerRegistry, list[EventRecord]]:
    registry = HandlerRegistry()
    seen: list[EventRecord] = []

    @registry.register(EventType.USER_AVAILABILITY_CHANGED, name="test.flip_availability")
    def flip(event: EventRecord) -> None:
        # A DB side effect, so double application would be observable.
        payload = event.payload
        assert isinstance(payload, UserAvailabilityChangedPayload)
        User.objects.filter(pk=payload.user_id).update(display_name=f"{event.id}-applied")
        seen.append(event)

    @registry.register(EventType.USER_AVAILABILITY_CHANGED, EventType.ITEM_ASSIGNED, name="test.second")
    def second(event: EventRecord) -> None:
        return None

    return registry, seen


def test_registry_rejects_duplicate_names() -> None:
    registry = HandlerRegistry()
    registry.register(EventType.ITEM_ASSIGNED, name="x")(lambda event: None)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(EventType.ITEM_SUBMITTED, name="x")(lambda event: None)


@pytest.mark.django_db
def test_replayed_event_applies_handler_once(reviewer: User, clock: FixedClock) -> None:
    registry, seen = _registry()
    event = _availability_event(reviewer, clock)

    first = deliver(event_id=event.pk, handler_name="test.flip_availability", registry=registry)
    second = deliver(event_id=event.pk, handler_name="test.flip_availability", registry=registry)

    assert (first, second) == (Delivery.APPLIED, Delivery.DUPLICATE)
    assert len(seen) == 1
    assert ProcessedEvent.objects.filter(event=event, handler="test.flip_availability").count() == 1
    reviewer.refresh_from_db()
    assert reviewer.display_name == f"{event.pk}-applied"


@pytest.mark.django_db
def test_handler_receives_typed_record(reviewer: User, clock: FixedClock) -> None:
    registry, seen = _registry()
    event = _availability_event(reviewer, clock, available=True)

    deliver(event_id=event.pk, handler_name="test.flip_availability", registry=registry)

    record = seen[0]
    assert record.type is EventType.USER_AVAILABILITY_CHANGED
    assert record.payload == UserAvailabilityChangedPayload(user_id=reviewer.pk, is_available=True)
    assert record.actor_id == reviewer.pk


@pytest.mark.django_db
def test_failed_handler_leaves_no_receipt(reviewer: User, clock: FixedClock) -> None:
    registry = HandlerRegistry()

    @registry.register(EventType.USER_AVAILABILITY_CHANGED, name="test.boom")
    def boom(event: EventRecord) -> None:
        raise RuntimeError("downstream unavailable")

    event = _availability_event(reviewer, clock)

    with pytest.raises(RuntimeError):
        deliver(event_id=event.pk, handler_name="test.boom", registry=registry)

    assert not ProcessedEvent.objects.filter(event=event).exists()


@pytest.mark.django_db
def test_dispatch_enqueues_each_matching_handler_and_advances_cursor(reviewer: User, clock: FixedClock) -> None:
    registry, _ = _registry()
    first = _availability_event(reviewer, clock)
    second = _availability_event(reviewer, clock)
    enqueue = Recorder()

    result = dispatch_pending(registry=registry, enqueue=enqueue)

    assert result.events == 2
    assert enqueue.calls == [
        (first.pk, "test.flip_availability"),
        (first.pk, "test.second"),
        (second.pk, "test.flip_availability"),
        (second.pk, "test.second"),
    ]
    cursor = OutboxCursor.objects.get(name="default")
    assert (cursor.last_txid, cursor.last_event_id) == (second.txid, second.pk)


@pytest.mark.django_db
def test_dispatch_twice_does_not_redeliver(reviewer: User, clock: FixedClock) -> None:
    registry, _ = _registry()
    _availability_event(reviewer, clock)
    enqueue = Recorder()

    dispatch_pending(registry=registry, enqueue=enqueue)
    again = dispatch_pending(registry=registry, enqueue=enqueue)

    assert again.events == 0
    assert len(enqueue.calls) == 2


@pytest.mark.django_db
def test_dispatch_skips_events_without_handlers(reviewer: User, clock: FixedClock) -> None:
    registry = HandlerRegistry()
    _availability_event(reviewer, clock)
    enqueue = Recorder()

    result = dispatch_pending(registry=registry, enqueue=enqueue)

    assert (result.events, result.deliveries, enqueue.calls) == (1, 0, [])


@pytest.mark.django_db
def test_redeliver_stale_requeues_missing_receipts(reviewer: User, clock: FixedClock) -> None:
    registry, _ = _registry()
    event = _availability_event(reviewer, clock)
    deliver(event_id=event.pk, handler_name="test.second", registry=registry)
    enqueue = Recorder()
    clock.advance(timedelta(minutes=10))

    count = redeliver_stale(registry=registry, enqueue=enqueue, clock=clock)

    assert count == 1
    assert enqueue.calls == [(event.pk, "test.flip_availability")]


@pytest.mark.django_db(transaction=True)
def test_dispatch_returns_at_once_while_another_dispatcher_holds_the_cursor(reviewer: User, clock: FixedClock) -> None:
    """Beat fires every 2 s; a dispatcher stuck on slow enqueues must not stack the next ones behind its lock."""
    registry, _ = _registry()
    OutboxCursor.objects.get_or_create(name=CURSOR_NAME)
    _availability_event(reviewer, clock)
    locked = threading.Event()
    release = threading.Event()

    def busy_dispatcher() -> None:
        try:
            with transaction.atomic():
                OutboxCursor.objects.select_for_update().get(name=CURSOR_NAME)
                locked.set()
                release.wait(timeout=3)
        finally:
            connection.close()

    thread = threading.Thread(target=busy_dispatcher)
    thread.start()
    assert locked.wait(timeout=10)
    try:
        result = dispatch_pending(registry=registry, enqueue=Recorder())
    finally:
        release.set()
        thread.join(timeout=10)

    assert (result.events, result.busy) == (0, True)


@pytest.mark.django_db(transaction=True)
def test_cursor_does_not_skip_late_committing_event(reviewer: User, clock: FixedClock) -> None:
    """Event A gets the lower id but commits after B. An id cursor would advance past A and lose it."""
    registry, _ = _registry()
    a_inserted = threading.Event()
    release_a = threading.Event()
    a_id: list[int] = []

    def slow_transaction() -> None:
        try:
            with transaction.atomic():
                a_id.append(_availability_event(reviewer, clock).pk)
                a_inserted.set()
                release_a.wait(timeout=10)
        finally:
            connection.close()

    thread = threading.Thread(target=slow_transaction)
    thread.start()
    assert a_inserted.wait(timeout=10)

    b = _availability_event(reviewer, clock)  # commits now, with a higher id than the still-open A
    enqueue = Recorder()
    dispatch_pending(registry=registry, enqueue=enqueue)  # A is still uncommitted here

    release_a.set()
    thread.join(timeout=10)

    # After A commits, a later pass must deliver it. Transactions in other databases on the same server can
    # briefly hold back the snapshot horizon, so allow a few passes.
    for _ in range(50):
        if {a_id[0], b.pk} <= {event_id for event_id, _ in enqueue.calls}:
            break
        dispatch_pending(registry=registry, enqueue=enqueue)
        threading.Event().wait(0.05)

    delivered = [event_id for event_id, name in enqueue.calls if name == "test.flip_availability"]
    assert a_id[0] < b.pk
    assert sorted(delivered) == sorted([a_id[0], b.pk])


@pytest.mark.django_db
def test_assignment_payload_round_trips(lead: User, clock: FixedClock) -> None:
    registry = HandlerRegistry()
    seen: list[EventRecord] = []
    registry.register(EventType.ITEM_ASSIGNED, name="test.seen")(seen.append)
    with transaction.atomic():
        event = record_event(
            type=EventType.ITEM_ASSIGNED,
            entity=EntityType.ITEM,
            entity_id=1,
            payload=ItemAssignedPayload(
                assignee_id=None, previous_assignee_id=None, mode=AssignmentMode.POOL, reason="nobody available"
            ),
            actor=None,
            at=clock.now(),
        )

    deliver(event_id=event.pk, handler_name="test.seen", registry=registry)

    payload = seen[0].payload
    assert isinstance(payload, ItemAssignedPayload)
    assert payload.mode is AssignmentMode.POOL
