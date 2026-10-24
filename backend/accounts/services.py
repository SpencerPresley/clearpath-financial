from dataclasses import dataclass

from django.db import transaction

from accounts.models import User
from audit.payloads import UserAvailabilityChangedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType


@dataclass(frozen=True)
class MeChanges:
    display_name: str | None = None
    is_available: bool | None = None


def update_me(*, actor: User, changes: MeChanges, clock: Clock = SYSTEM_CLOCK) -> None:
    """A user edits their own profile. Availability feeds auto-assignment, so changing it is recorded."""
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=actor.pk)
        fields: list[str] = []
        if changes.display_name is not None and changes.display_name != user.display_name:
            user.display_name = changes.display_name
            fields.append("display_name")
        if changes.is_available is not None and changes.is_available != user.is_available:
            user.is_available = changes.is_available
            fields.append("is_available")
            record_event(
                type=EventType.USER_AVAILABILITY_CHANGED,
                entity=EntityType.USER,
                entity_id=user.pk,
                payload=UserAvailabilityChangedPayload(user_id=user.pk, is_available=changes.is_available),
                actor=actor,
                at=clock.now(),
            )
        if fields:
            user.save(update_fields=fields)
            actor.refresh_from_db(fields=fields)
