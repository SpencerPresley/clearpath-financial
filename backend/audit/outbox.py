"""Outbox dispatch: side effects run from events, at least once, applied exactly once per handler.

Register a handler in your app's `handlers.py` (autodiscovered at startup):

    from audit.outbox import EventRecord, handles

    @handles(EventType.ITEM_SUBMITTED, name="checks.llm_prereview")
    def start_llm_prereview(event: EventRecord) -> None: ...

`name` is the idempotency key, stored in `ProcessedEvent`; never rename a deployed handler. A handler runs
inside a transaction together with its receipt, so DB side effects apply exactly once. A handler with an
external side effect (an LLM call) should enqueue its own idempotent task rather than call out inline.

Delivery: the beat task `audit.dispatch_outbox` calls `dispatch_pending`, which enqueues one
`audit.run_event_handler(event_id, handler_name)` task per (event, matching handler) and advances the cursor.
`redeliver_stale` re-enqueues deliveries that never produced a receipt (a handler that kept failing).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from django.db import connection, transaction
from django.db.models import Exists, OuterRef

from audit.models import Event, OutboxCursor, ProcessedEvent
from audit.payloads import EventPayload, parse_payload
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType, ItemStatus

logger = logging.getLogger(__name__)

CURSOR_NAME: Final = "default"


@dataclass(frozen=True)
class EventRecord:
    """What a handler receives: the event with its payload parsed into the registered model."""

    id: int
    type: EventType
    entity: EntityType
    entity_id: int
    item_id: int | None
    actor_id: int | None
    at: datetime
    from_status: ItemStatus | None
    to_status: ItemStatus | None
    payload: EventPayload

    @classmethod
    def from_event(cls, event: Event) -> EventRecord:
        event_type = EventType(event.type)
        return cls(
            id=event.pk,
            type=event_type,
            entity=EntityType(event.entity),
            entity_id=event.entity_id,
            item_id=event.item_id,  # pyrefly: ignore[missing-attribute]
            actor_id=event.actor_id,  # pyrefly: ignore[missing-attribute]
            at=event.at,
            from_status=ItemStatus(event.from_status) if event.from_status else None,
            to_status=ItemStatus(event.to_status) if event.to_status else None,
            payload=parse_payload(event_type, event.payload),
        )


type Handler = Callable[[EventRecord], None]
type Enqueue = Callable[[int, str], None]


@dataclass(frozen=True)
class HandlerSpec:
    name: str
    event_types: frozenset[EventType]
    func: Handler


class HandlerRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, HandlerSpec] = {}

    def register(self, *event_types: EventType, name: str) -> Callable[[Handler], Handler]:
        if not event_types:
            raise ValueError("a handler needs at least one event type")

        def decorator(func: Handler) -> Handler:
            if name in self._by_name:
                raise ValueError(f"handler {name!r} is already registered")
            self._by_name[name] = HandlerSpec(name=name, event_types=frozenset(event_types), func=func)
            return func

        return decorator

    def for_type(self, event_type: EventType) -> tuple[HandlerSpec, ...]:
        return tuple(spec for spec in self._by_name.values() if event_type in spec.event_types)

    def get(self, name: str) -> HandlerSpec:
        return self._by_name[name]

    def all(self) -> tuple[HandlerSpec, ...]:
        return tuple(self._by_name.values())


REGISTRY: Final = HandlerRegistry()
handles: Final = REGISTRY.register


class Delivery(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class DispatchResult:
    events: int
    deliveries: int


def enqueue_handler(event_id: int, handler_name: str) -> None:
    from audit.tasks import run_event_handler  # noqa: PLC0415  # tasks imports this module

    run_event_handler.delay(event_id, handler_name)


# Events visible to dispatch: from transactions older than every transaction still running (so nothing
# can later commit before them in (txid, id) order), plus the dispatcher's own transaction's events.
_PENDING_SQL = """
    SELECT id, txid, type FROM audit_event
    WHERE (txid, id) > (%s, %s)
      AND (txid < pg_snapshot_xmin(pg_current_snapshot())::text::bigint
           OR txid = pg_current_xact_id_if_assigned()::text::bigint)
    ORDER BY txid, id
    LIMIT %s
"""


def dispatch_pending(
    *, registry: HandlerRegistry = REGISTRY, enqueue: Enqueue = enqueue_handler, batch_size: int = 500
) -> DispatchResult:
    """Enqueue every matching handler for events past the cursor, then advance it. Safe to run
    concurrently (the cursor row is locked) and to crash midway (deliveries are idempotent)."""
    with transaction.atomic():
        OutboxCursor.objects.get_or_create(name=CURSOR_NAME)
        cursor = OutboxCursor.objects.select_for_update().get(name=CURSOR_NAME)
        with connection.cursor() as db:
            db.execute(_PENDING_SQL, [cursor.last_txid, cursor.last_event_id, batch_size])
            rows: list[tuple[int, int, str]] = db.fetchall()
        deliveries = 0
        for event_id, _txid, event_type in rows:
            for spec in registry.for_type(EventType(event_type)):
                enqueue(event_id, spec.name)
                deliveries += 1
        if rows:
            last_id, last_txid, _ = rows[-1]
            cursor.last_txid, cursor.last_event_id = last_txid, last_id
            cursor.save(update_fields=["last_txid", "last_event_id"])
    return DispatchResult(events=len(rows), deliveries=deliveries)


_CLAIM_SQL = """
    INSERT INTO audit_processedevent (event_id, handler, processed_at)
    VALUES (%s, %s, now())
    ON CONFLICT (event_id, handler) DO NOTHING
    RETURNING id
"""


def deliver(*, event_id: int, handler_name: str, registry: HandlerRegistry = REGISTRY) -> Delivery:
    """Apply one handler to one event, once. A concurrent duplicate blocks on the receipt's unique key
    until the first commits, then sees it and returns DUPLICATE."""
    spec = registry.get(handler_name)
    with transaction.atomic():
        with connection.cursor() as db:
            db.execute(_CLAIM_SQL, [event_id, handler_name])
            claimed = db.fetchone() is not None
        if not claimed:
            return Delivery.DUPLICATE
        spec.func(EventRecord.from_event(Event.objects.get(pk=event_id)))
    return Delivery.APPLIED


def redeliver_stale(
    *,
    registry: HandlerRegistry = REGISTRY,
    enqueue: Enqueue = enqueue_handler,
    clock: Clock = SYSTEM_CLOCK,
    older_than: timedelta = timedelta(minutes=5),
    lookback: timedelta = timedelta(days=1),
) -> int:
    """Re-enqueue (event, handler) pairs with no receipt, for events between `lookback` and `older_than`
    ago. Catches handlers whose retries ran out; idempotency makes the repeat harmless."""
    now = clock.now()
    count = 0
    for spec in registry.all():
        missing = (
            Event.objects.filter(
                type__in=[t.value for t in spec.event_types], at__gte=now - lookback, at__lte=now - older_than
            )
            .exclude(Exists(ProcessedEvent.objects.filter(event=OuterRef("pk"), handler=spec.name)))
            .order_by("id")
            .values_list("id", flat=True)
        )
        for event_id in missing:
            enqueue(event_id, spec.name)
            count += 1
    if count:
        logger.warning("outbox redelivered %d stale deliveries", count)
    return count
