from dataclasses import dataclass

from django.db.models import Q

from accounts.models import User
from assistant.llm import assistant_configured
from core.domain import Role
from core.errors import NotFound
from core.permissions import effective_roles, require_role
from reviews.assignment import ReviewerLoad, auto_assign_pool, weighted_loads
from reviews.models import QUEUE_STATUSES, ReviewItem


@dataclass(frozen=True)
class Me:
    id: int
    email: str
    display_name: str
    roles: tuple[Role, ...]
    effective_roles: tuple[Role, ...]
    is_available: bool
    assistant_configured: bool


@dataclass(frozen=True)
class UserRow:
    id: int
    email: str
    display_name: str
    roles: tuple[Role, ...]
    is_available: bool
    is_active: bool


_ROLE_ORDER = list(Role)


def _sorted(roles: object) -> tuple[Role, ...]:
    return tuple(sorted((Role(r) for r in roles), key=_ROLE_ORDER.index))  # pyrefly: ignore[not-iterable]


def get_me(user: User) -> Me:
    return Me(
        id=user.pk,
        email=user.email,
        display_name=user.display_name,
        roles=_sorted(user.roles),
        effective_roles=_sorted(effective_roles(user)),
        is_available=user.is_available,
        assistant_configured=assistant_configured(),
    )


def _user_row(u: User) -> UserRow:
    return UserRow(
        id=u.pk,
        email=u.email,
        display_name=u.display_name,
        roles=_sorted(u.roles),
        is_available=u.is_available,
        is_active=u.is_active,
    )


def list_users(*, role: Role | None = None, include_inactive: bool = False) -> tuple[UserRow, ...]:
    qs = User.objects.order_by("display_name", "email")
    if role is not None:
        qs = qs.filter(roles__contains=[role.value])
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return tuple(_user_row(u) for u in qs)


def get_user(user_id: int) -> UserRow:
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        raise NotFound.entity("user", user_id)
    return _user_row(user)


@dataclass(frozen=True)
class WorkloadRow:
    user_id: int
    name: str
    is_available: bool
    auto_assigned: bool  # in lowest-load assignment's pool right now
    open_items: int
    weighted_load: int


def reviewer_workload(*, viewer: User) -> tuple[WorkloadRow, ...]:
    """Per-reviewer open load for the lead (spec §1, workload balance), heaviest first. The load is
    `reviews.assignment.weighted_loads`, the number auto-assignment ranks by. Lists every active user granted
    `reviewer`, plus anyone else holding open items (a lead who claimed some, who auto-assignment skips)."""
    require_role(viewer, Role.LEAD, Role.ADMIN)
    holders = ReviewItem.objects.filter(status__in=QUEUE_STATUSES, assignee__isnull=False).values("assignee_id")
    people = list(
        User.objects.filter(is_active=True).filter(Q(roles__contains=[Role.REVIEWER.value]) | Q(pk__in=holders))
    )
    loads = weighted_loads(u.pk for u in people)
    pool = set(auto_assign_pool().filter(pk__in=[u.pk for u in people]).values_list("pk", flat=True))
    rows = [
        WorkloadRow(
            user_id=u.pk,
            name=u.display_name or u.email,
            is_available=u.is_available,
            auto_assigned=u.pk in pool,
            open_items=(load := loads.get(u.pk, ReviewerLoad(0, 0))).open_items,
            weighted_load=load.weighted,
        )
        for u in people
    ]
    return tuple(sorted(rows, key=lambda r: (-r.weighted_load, -r.open_items, r.name.casefold(), r.user_id)))
