"""Create or reset the demo logins: one user per role, all with DEMO_USER_PASSWORD.

Idempotent: re-running resets each demo user's roles, name, availability, and password. Evaluators get app
roles only; none of these accounts can reach django-admin.
"""

from typing import Any, Final

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from config.settings.base import env
from core.domain import Role

DEMO_USERS: Final[dict[Role, str]] = {
    Role.MARKETER: "Morgan Marketer",
    Role.REVIEWER: "Riley Reviewer",
    Role.LEAD: "Lee Lead",
    Role.ADMIN: "Avery Admin",
}


def demo_email(role: Role) -> str:
    return f"{role.value}@clearpath.demo"


class Command(BaseCommand):
    help = "Create or reset one demo user per role (password from DEMO_USER_PASSWORD)."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401, ARG002  # BaseCommand.handle signature
        secret = env.demo_user_password
        if secret is None or not secret.get_secret_value():
            raise CommandError("Set DEMO_USER_PASSWORD to seed the demo users.")
        password = secret.get_secret_value()
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(f"DEMO_USER_PASSWORD is too weak: {' '.join(exc.messages)}") from exc
        with transaction.atomic():
            for role, name in DEMO_USERS.items():
                user, created = User.objects.get_or_create(email=demo_email(role), defaults={"display_name": name})
                user.display_name = name
                user.roles = [role.value]
                user.is_active = True
                user.is_available = True
                user.is_staff = False
                user.is_superuser = False
                user.set_password(password)
                user.save()
                self.stdout.write(f"{'created' if created else 'reset'} {user.email} ({role.value})")
