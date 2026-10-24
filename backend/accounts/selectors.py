from dataclasses import dataclass

from accounts.models import User
from core.domain import Role
from core.permissions import effective_roles


@dataclass(frozen=True)
class Me:
    id: int
    email: str
    display_name: str
    roles: tuple[Role, ...]
    effective_roles: tuple[Role, ...]
    is_available: bool


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
    )


def list_users(*, role: Role | None = None, include_inactive: bool = False) -> tuple[UserRow, ...]:
    qs = User.objects.order_by("display_name", "email")
    if role is not None:
        qs = qs.filter(roles__contains=[role.value])
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return tuple(
        UserRow(
            id=u.pk,
            email=u.email,
            display_name=u.display_name,
            roles=_sorted(u.roles),
            is_available=u.is_available,
            is_active=u.is_active,
        )
        for u in qs
    )
