import pytest
from django.db import IntegrityError, connection, transaction

from accounts.models import User
from audit.models import Event
from audit.payloads import PAYLOADS, ItemAssignedPayload, UserAvailabilityChangedPayload
from audit.services import record_event
from core.clock import FixedClock
from core.domain import AssignmentMode, EntityType, EventType, ItemStatus


def _assigned(actor: User, clock: FixedClock) -> Event:
    return record_event(
        type=EventType.ITEM_ASSIGNED,
        entity=EntityType.ITEM,
        entity_id=1,
        payload=ItemAssignedPayload(
            assignee_id=actor.pk, previous_assignee_id=None, mode=AssignmentMode.MANUAL, reason="test"
        ),
        actor=actor,
        at=clock.now(),
    )


def test_every_event_type_has_a_payload_model() -> None:
    assert set(PAYLOADS) == set(EventType)


@pytest.mark.django_db
def test_record_event_stores_typed_payload_and_status_change(lead: User, clock: FixedClock) -> None:
    event = record_event(
        type=EventType.ITEM_ASSIGNED,
        entity=EntityType.ITEM,
        entity_id=42,
        payload=ItemAssignedPayload(
            assignee_id=7, previous_assignee_id=None, mode=AssignmentMode.MANUAL, reason="Dana: load 4 vs Sam 7"
        ),
        actor=lead,
        at=clock.now(),
        from_status=ItemStatus.SUBMITTED,
        to_status=ItemStatus.IN_REVIEW,
    )
    event.refresh_from_db()

    assert event.type == "item.assigned"
    assert event.payload == {
        "assignee_id": 7,
        "previous_assignee_id": None,
        "mode": "manual",
        "reason": "Dana: load 4 vs Sam 7",
    }
    assert (event.from_status, event.to_status) == ("submitted", "in_review")
    assert event.at == clock.now()
    assert event.txid > 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sql", ["UPDATE audit_event SET type = 'x' WHERE id = %s", "DELETE FROM audit_event WHERE id = %s"]
)
def test_event_rejects_update_and_delete(lead: User, clock: FixedClock, sql: str) -> None:
    with transaction.atomic():
        event = _assigned(lead, clock)

    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, [event.pk])


@pytest.mark.django_db(transaction=True)
def test_record_event_outside_atomic_raises(lead: User, clock: FixedClock) -> None:
    with pytest.raises(RuntimeError, match=r"transaction\.atomic"):
        _assigned(lead, clock)


@pytest.mark.django_db
def test_record_event_rejects_payload_of_another_type(lead: User, clock: FixedClock) -> None:
    with pytest.raises(TypeError, match="UserAvailabilityChangedPayload"):
        record_event(
            type=EventType.ITEM_ASSIGNED,
            entity=EntityType.USER,
            entity_id=lead.pk,
            payload=UserAvailabilityChangedPayload(user_id=lead.pk, is_available=False),
            actor=lead,
            at=clock.now(),
        )
