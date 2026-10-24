"""Role checks, enforced in services (spec §4.3 Auth and roles).

`User.roles` stores what was granted. Permission checks expand implied roles (a lead can do everything a
reviewer can, product-spec "Roles"); SQL that selects people by role (e.g. the auto-assignment pool) uses
the stored roles, so a lead isn't auto-assigned work unless they were also granted `reviewer`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from pydantic import JsonValue

from core.domain import Role
from core.errors import NotPermitted

if TYPE_CHECKING:
    from accounts.models import User

IMPLIED_ROLES: Final[Mapping[Role, frozenset[Role]]] = {Role.LEAD: frozenset({Role.REVIEWER})}

# Who may act as a reviewer. Pass to require_role for review actions.
REVIEW_ROLES: Final = (Role.REVIEWER,)


def effective_roles(user: User) -> frozenset[Role]:
    if not user.is_active:
        return frozenset()
    granted = {Role(r) for r in user.roles}
    for role in tuple(granted):
        granted |= IMPLIED_ROLES.get(role, frozenset())
    return frozenset(granted)


def has_role(user: User, *roles: Role) -> bool:
    return not effective_roles(user).isdisjoint(roles)


def require_role(user: User, *roles: Role) -> None:
    if not has_role(user, *roles):
        names: list[JsonValue] = [str(r) for r in roles]
        raise NotPermitted(
            f"This needs the {' or '.join(str(r) for r in roles)} role.",
            details={"required_any_of": names},
        )
