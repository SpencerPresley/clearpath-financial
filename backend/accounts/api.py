from django.http import HttpRequest
from ninja import Router

from accounts.models import User
from accounts.schemas import MeOut
from accounts.selectors import Me, get_me
from core.schemas import ERRORS

me_router = Router(tags=["me"])
admin_router = Router(tags=["admin"])


def current_user(request: HttpRequest) -> User:
    """The authenticated user. Every operation behind `django_auth` has one."""
    user = request.user
    assert isinstance(user, User)  # noqa: S101  # guaranteed by django_auth
    return user


@me_router.get("/me", response={200: MeOut, **ERRORS}, operation_id="getMe")
def me(request: HttpRequest) -> Me:
    return get_me(current_user(request))
