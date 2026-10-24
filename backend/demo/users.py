"""The demo's people: create or reset each persona's account.

Every persona can sign in with the demo password. It comes from DEMO_USER_PASSWORD when set (production overrides
it), otherwise it's the password documented in docs/demo.md, so a fresh environment is usable straight away. None
of these accounts can reach django-admin.
"""

from collections.abc import Iterable
from typing import Final

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User
from config.settings.base import env
from core.errors import InvalidInput
from demo.story import Persona

DOCUMENTED_PASSWORD: Final = "ClearPath-demo-2026"  # noqa: S105  # public by design: docs/demo.md


def demo_password() -> str:
    """DEMO_USER_PASSWORD, else the documented one where that's allowed (not in production: it's public)."""
    secret = env.demo_user_password
    value = secret.get_secret_value() if secret is not None else ""
    if settings.DEMO_PASSWORD_DEFAULT_ALLOWED:
        return value or DOCUMENTED_PASSWORD
    if not value:
        raise InvalidInput.for_field(
            "password", "DEMO_USER_PASSWORD isn't set. This environment needs its own demo password."
        )
    if value == DOCUMENTED_PASSWORD:
        raise InvalidInput.for_field(
            "password", "DEMO_USER_PASSWORD is the published demo password. This environment needs its own."
        )
    return value


def check_password_strength(password: str) -> None:
    try:
        validate_password(password)
    except ValidationError as exc:
        raise InvalidInput.for_field("password", f"DEMO_USER_PASSWORD is too weak: {' '.join(exc.messages)}") from exc


def upsert_personas(personas: Iterable[Persona], *, password: str) -> dict[str, User]:
    """Create each persona's user or reset it to the catalog: name, roles, active, available, password, and no
    assignment history (so auto-assignment replays the same way). Returns users by persona key."""
    check_password_strength(password)
    users: dict[str, User] = {}
    with transaction.atomic():
        for persona in personas:
            user, _ = User.objects.get_or_create(email=persona.email, defaults={"display_name": persona.name})
            user.display_name = persona.name
            user.roles = [role.value for role in persona.roles]
            user.is_active = True
            user.is_available = True
            user.is_staff = False
            user.is_superuser = False
            user.last_assigned_at = None
            # Only when it differs: a new hash changes the session auth hash, which would sign out everyone using
            # the demo (including the admin who pressed Reset) on every reset.
            if not user.check_password(password):
                user.set_password(password)
            user.save()
            users[persona.key] = user
    return users
