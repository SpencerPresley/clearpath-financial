"""Create or reset the demo logins without touching any other data: every demo persona (one documented login per
role plus the rest of the team), all with the demo password (DEMO_USER_PASSWORD, or the documented default).

Idempotent: re-running resets each persona's roles, name, availability and password. Evaluators get app roles
only; none of these accounts can reach django-admin. `seed_demo` does this too, along with the demo data.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core.errors import InvalidInput
from demo.content.people import PERSONAS
from demo.users import demo_password, upsert_personas


class Command(BaseCommand):
    help = "Create or reset the demo personas' logins (password from DEMO_USER_PASSWORD, or the documented default)."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401, ARG002  # BaseCommand.handle signature
        try:
            users = upsert_personas(PERSONAS, password=demo_password())
        except InvalidInput as exc:
            raise CommandError(exc.message) from exc
        for persona in PERSONAS:
            self.stdout.write(f"{users[persona.key].email} ({', '.join(r.value for r in persona.roles)})")
