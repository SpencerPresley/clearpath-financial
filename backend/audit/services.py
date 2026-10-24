from datetime import datetime

from django.db import connection

from accounts.models import User
from audit.models import Event
from audit.payloads import PAYLOADS, EventPayload
from core.domain import EntityType, EventType, ItemStatus


def record_event(  # noqa: PLR0913  # every argument is a column of the record
    *,
    type: EventType,  # noqa: A002  # the event's type is the domain word
    entity: EntityType,
    entity_id: int,
    payload: EventPayload,
    actor: User | None,
    at: datetime,
    item_id: int | None = None,
    from_status: ItemStatus | None = None,
    to_status: ItemStatus | None = None,
) -> Event:
    """Append an event. Call it inside the service's `transaction.atomic()` so the state change and its
    event commit together; it refuses to run in autocommit mode, where they could come apart."""
    if not connection.in_atomic_block:
        raise RuntimeError("record_event must run inside transaction.atomic() with the state change it records")
    expected = PAYLOADS[type]
    if not isinstance(payload, expected):
        raise TypeError(f"{type} needs {expected.__name__}, got {payload.__class__.__name__}")
    return Event.objects.create(
        type=type.value,
        entity=entity.value,
        entity_id=entity_id,
        item_id=item_id,
        actor=actor,
        at=at,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value if to_status else None,
        payload=payload.model_dump(mode="json"),
    )
