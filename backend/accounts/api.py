from django.http import HttpRequest
from ninja import Router, Status

from accounts import selectors, services
from accounts.models import User
from accounts.schemas import DemoResetOut, MeOut, MeUpdateIn, UserCreateIn, UserOut, UserUpdateIn
from core.domain import Role
from core.errors import NotImplementedYet
from core.schemas import ERRORS, STUB_ERRORS

me_router = Router(tags=["me"])
admin_router = Router(tags=["admin"])


def current_user(request: HttpRequest) -> User:
    """The authenticated user. Every operation behind `django_auth` has one."""
    user = request.user
    assert isinstance(user, User)  # noqa: S101  # guaranteed by django_auth
    return user


@me_router.get("/me", response={200: MeOut, **ERRORS}, operation_id="getMe")
def me(request: HttpRequest) -> selectors.Me:
    return selectors.get_me(current_user(request))


@me_router.patch("/me", response={200: MeOut, **ERRORS}, operation_id="updateMe")
def update_me(request: HttpRequest, body: MeUpdateIn) -> selectors.Me:
    """Display name and availability (out-of-office reviewers are skipped by auto-assignment)."""
    user = current_user(request)
    services.update_me(
        actor=user, changes=services.MeChanges(display_name=body.display_name, is_available=body.is_available)
    )
    return selectors.get_me(user)


@admin_router.get("/users", response={200: list[UserOut], **ERRORS}, operation_id="listUsers")
def list_users(
    request: HttpRequest, role: Role | None = None, include_inactive: bool = False
) -> list[selectors.UserRow]:
    """People for pickers (assignee, @mention) and the admin user list."""
    return list(selectors.list_users(role=role, include_inactive=include_inactive))


@admin_router.post("/admin/users", response={201: UserOut, **STUB_ERRORS}, operation_id="createUser")
def create_user(request: HttpRequest, body: UserCreateIn) -> Status[UserOut]:
    """Admins provision accounts (no public signup). [admin user management]"""
    raise NotImplementedYet("user management")


@admin_router.patch("/admin/users/{int:user_id}", response={200: UserOut, **STUB_ERRORS}, operation_id="updateUser")
def update_user(request: HttpRequest, user_id: int, body: UserUpdateIn) -> UserOut:
    """[admin user management]"""
    raise NotImplementedYet("user management")


@admin_router.post("/admin/demo/reset", response={202: DemoResetOut, **STUB_ERRORS}, operation_id="resetDemo")
def reset_demo(request: HttpRequest) -> Status[DemoResetOut]:
    """Wipe and re-seed the demo data. Admins only; the UI confirms first. [workstream L]"""
    raise NotImplementedYet("demo reset")
