from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from audit.payloads import (
    UserActiveChangedPayload,
    UserAvailabilityChangedPayload,
    UserCreatedPayload,
    UserRolesChangedPayload,
)
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType, Role
from core.errors import Conflict, InvalidInput, NotFound
from core.permissions import require_role

_ROLE_ORDER = list(Role)


def _ordered(roles: tuple[Role, ...] | list[str]) -> tuple[Role, ...]:
    return tuple(sorted({Role(r) for r in roles}, key=_ROLE_ORDER.index))


def _set_availability(user: User, *, is_available: bool, actor: User, at: datetime) -> bool:
    """Availability feeds auto-assignment, so every change is recorded. Returns whether it changed."""
    if is_available == user.is_available:
        return False
    user.is_available = is_available
    record_event(
        type=EventType.USER_AVAILABILITY_CHANGED,
        entity=EntityType.USER,
        entity_id=user.pk,
        payload=UserAvailabilityChangedPayload(user_id=user.pk, is_available=is_available),
        actor=actor,
        at=at,
    )
    return True


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
        if changes.is_available is not None and _set_availability(
            user, is_available=changes.is_available, actor=actor, at=clock.now()
        ):
            fields.append("is_available")
        if fields:
            user.save(update_fields=fields)
            actor.refresh_from_db(fields=fields)


# --- admin user management (spec §1, Admin: Users) ---------------------------------------------------------------


@dataclass(frozen=True)
class NewUser:
    email: str
    display_name: str
    roles: tuple[Role, ...]
    password: str


def create_user(*, actor: User, new: NewUser, clock: Clock = SYSTEM_CLOCK) -> int:
    """An admin provisions an account (there is no public signup). Records USER_CREATED. Returns the user id."""
    require_role(actor, Role.ADMIN)
    email = new.email.strip().lower()
    candidate = User(email=email, display_name=new.display_name)
    try:
        validate_password(new.password, user=candidate)
    except ValidationError as exc:
        raise InvalidInput.for_field("password", " ".join(exc.messages)) from exc
    roles = _ordered(new.roles)
    with transaction.atomic():
        if User.objects.filter(email__iexact=email).exists():
            raise InvalidInput.for_field("email", "Someone already has this email.")
        user = User.objects.create_user(
            email=email, password=new.password, display_name=new.display_name, roles=[r.value for r in roles]
        )
        record_event(
            type=EventType.USER_CREATED,
            entity=EntityType.USER,
            entity_id=user.pk,
            payload=UserCreatedPayload(user_id=user.pk, email=email, roles=roles),
            actor=actor,
            at=clock.now(),
        )
    return user.pk


@dataclass(frozen=True)
class UserChanges:
    display_name: str | None = None
    roles: tuple[Role, ...] | None = None
    is_active: bool | None = None
    is_available: bool | None = None


def _name(user: User) -> str:
    return user.display_name or user.email


def update_user(*, actor: User, user_id: int, changes: UserChanges, clock: Clock = SYSTEM_CLOCK) -> None:
    """An admin changes someone's roles, active flag, availability, or name; one event per recorded change.

    There is always an active admin: an admin can't deactivate their own account, and the last active admin keeps
    the admin role. The active admins' rows are locked before they're counted, so two admins demoting each other
    at once can't both pass the check (the second waits, then counts one)."""
    require_role(actor, Role.ADMIN)
    now = clock.now()
    with transaction.atomic():
        admins = set(
            User.objects.select_for_update()
            .filter(is_active=True, roles__contains=[Role.ADMIN.value])
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        user = User.objects.select_for_update().filter(pk=user_id).first()
        if user is None:
            raise NotFound.entity("user", user_id)
        before = _ordered(user.roles)
        after = before if changes.roles is None else _ordered(changes.roles)
        active = user.is_active if changes.is_active is None else changes.is_active

        if not active and user.is_active and user.pk == actor.pk:
            raise Conflict("You can't deactivate your own account. Ask another admin.")
        loses_admin = user.pk in admins and (not active or Role.ADMIN not in after)
        if loses_admin and not admins - {user.pk}:
            raise Conflict(f"{_name(user)} is the only admin. Make someone else an admin first.")

        fields: list[str] = []
        if changes.display_name is not None and changes.display_name != user.display_name:
            user.display_name = changes.display_name
            fields.append("display_name")
        if after != before:
            user.roles = [r.value for r in after]
            fields.append("roles")
            record_event(
                type=EventType.USER_ROLES_CHANGED,
                entity=EntityType.USER,
                entity_id=user.pk,
                payload=UserRolesChangedPayload(user_id=user.pk, before=before, after=after),
                actor=actor,
                at=now,
            )
        if active != user.is_active:
            user.is_active = active
            fields.append("is_active")
            record_event(
                type=EventType.USER_ACTIVE_CHANGED,
                entity=EntityType.USER,
                entity_id=user.pk,
                payload=UserActiveChangedPayload(user_id=user.pk, is_active=active),
                actor=actor,
                at=now,
            )
        if changes.is_available is not None and _set_availability(
            user, is_available=changes.is_available, actor=actor, at=now
        ):
            fields.append("is_available")
        if fields:
            user.save(update_fields=fields)
