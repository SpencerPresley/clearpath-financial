"""Seed the demo: personas, partners, offer terms, ~40 items with their histories, and the sample tracker import.

`seed_demo` on an empty database seeds it; on a database that already has items it does nothing (so a deploy can
run it every time). `seed_demo --reset` wipes the domain data first, which is what the admin's Reset demo runs.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.errors import InvalidInput
from demo.reset import has_demo_data, reset_demo
from demo.runner import SeedError


class Command(BaseCommand):
    help = "Seed the demo data on an empty database; --reset wipes the domain data and reseeds."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--reset", action="store_true", help="Wipe items, partners, terms, events and reseed.")

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401, ARG002  # BaseCommand.handle signature
        if has_demo_data() and not options["reset"]:
            self.stdout.write("Items already exist; nothing seeded. Run with --reset to wipe and reseed.")
            return
        try:
            result = reset_demo()
        except InvalidInput as exc:
            raise CommandError(exc.message) from exc
        except SeedError as exc:
            raise CommandError(f"The demo catalog couldn't be seeded (nothing changed): {exc}") from exc
        self.stdout.write(
            f"Seeded {result.items} items, {result.legacy_items} legacy tracker items, {result.users} people."
        )
