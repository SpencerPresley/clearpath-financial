import pytest

from accounts.models import User
from core.domain import Role
from core.errors import NotPermitted
from core.permissions import effective_roles, has_role, require_role


def _user(*roles: Role) -> User:
    return User(email="x@clearpath.test", roles=list(roles))


def test_lead_implies_reviewer() -> None:
    assert effective_roles(_user(Role.LEAD)) == frozenset({Role.LEAD, Role.REVIEWER})


def test_has_role_is_any_of() -> None:
    assert has_role(_user(Role.MARKETER), Role.REVIEWER, Role.MARKETER)
    assert not has_role(_user(Role.MARKETER), Role.REVIEWER)


def test_require_role_passes_lead_for_reviewer_actions() -> None:
    require_role(_user(Role.LEAD), Role.REVIEWER)


def test_require_role_raises_not_permitted_with_required_roles() -> None:
    with pytest.raises(NotPermitted) as caught:
        require_role(_user(Role.MARKETER), Role.REVIEWER)

    assert caught.value.code == "not_permitted"
    assert caught.value.details == {"required_any_of": ["reviewer"]}


def test_admin_implies_nothing_else() -> None:
    assert effective_roles(_user(Role.ADMIN)) == frozenset({Role.ADMIN})


def test_inactive_user_has_no_roles() -> None:
    user = _user(Role.LEAD)
    user.is_active = False

    assert effective_roles(user) == frozenset()
