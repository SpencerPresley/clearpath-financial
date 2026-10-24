from django.http import HttpRequest
from ninja import Router, Status

from accounts import selectors, services
from accounts.models import User
from accounts.schemas import DemoResetOut, MeOut, MeUpdateIn, UserCreateIn, UserOut, UserUpdateIn, WorkloadOut
from core.domain import Role
from core.schemas import ERRORS
from demo.services import DemoResetJob, get_reset, request_reset

me_router = Router(tags=["me"])
admin_router = Router(tags=["admin"])
users_router = Router(tags=["users"])  # pickers: every signed-in role


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


@users_router.get("/users", response={200: list[UserOut], **ERRORS}, operation_id="listUsers")
def list_users(
    request: HttpRequest, role: Role | None = None, include_inactive: bool = False
) -> list[selectors.UserRow]:
    """People for pickers (assignee, @mention) and the admin user list."""
    return list(selectors.list_users(role=role, include_inactive=include_inactive))


@users_router.get("/users/workload", response={200: list[WorkloadOut], **ERRORS}, operation_id="getReviewerWorkload")
def reviewer_workload(request: HttpRequest) -> list[selectors.WorkloadRow]:
    """Open items and weighted load per reviewer, heaviest first: the load lowest-load assignment ranks by.
    Leads and admins."""
    return list(selectors.reviewer_workload(viewer=current_user(request)))


@admin_router.post("/admin/users", response={201: UserOut, **ERRORS}, operation_id="createUser")
def create_user(request: HttpRequest, body: UserCreateIn) -> Status[selectors.UserRow]:
    """Admins provision accounts (no public signup). Records USER_CREATED. 422 on `body.email` if it's taken."""
    new = services.NewUser(
        email=body.email, display_name=body.display_name, roles=tuple(body.roles), password=body.password
    )
    user_id = services.create_user(actor=current_user(request), new=new)
    return Status(201, selectors.get_user(user_id))


@admin_router.patch("/admin/users/{int:user_id}", response={200: UserOut, **ERRORS}, operation_id="updateUser")
def update_user(request: HttpRequest, user_id: int, body: UserUpdateIn) -> selectors.UserRow:
    """Change roles, active, availability, or name. Records USER_ROLES_CHANGED / USER_ACTIVE_CHANGED /
    USER_AVAILABILITY_CHANGED. 409 if it would leave no active admin, or an admin deactivates themselves."""
    changes = services.UserChanges(
        display_name=body.display_name,
        roles=None if body.roles is None else tuple(body.roles),
        is_active=body.is_active,
        is_available=body.is_available,
    )
    services.update_user(actor=current_user(request), user_id=user_id, changes=changes)
    return selectors.get_user(user_id)


@admin_router.post("/admin/demo/reset", response={202: DemoResetOut, **ERRORS}, operation_id="resetDemo")
def reset_demo(request: HttpRequest) -> Status[DemoResetJob]:
    """Wipe the demo data and seed it again, as a background job (poll `getDemoReset`). Admins only; the UI
    confirms first. While a reset is queued or running, this returns that one instead of starting another. People
    and sessions are kept, so you stay signed in."""
    return Status(202, request_reset(actor=current_user(request)))


@admin_router.get(
    "/admin/demo/resets/{int:reset_id}", response={200: DemoResetOut, **ERRORS}, operation_id="getDemoReset"
)
def get_demo_reset(request: HttpRequest, reset_id: int) -> DemoResetJob:
    """How a Reset demo job is going. Admins only."""
    return get_reset(viewer=current_user(request), reset_id=reset_id)
