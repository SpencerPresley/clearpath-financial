"""ninja's `export_openapi_schema`, without Django's system checks.

Exporting the schema only introspects the API, but `manage.py` runs system checks first, and GeneratedField's
check opens a database connection. The api-contract drift job has no database, so the export must not need
one. System checks still run in backend CI (`manage.py check`, the test suite), with Postgres.

Overrides ninja's command because `core` is listed before `ninja` in INSTALLED_APPS (earlier apps win).
"""

from typing import ClassVar

from ninja.management.commands.export_openapi_schema import Command as NinjaExportCommand


class Command(NinjaExportCommand):
    requires_system_checks: ClassVar[list[str]] = []  # pyrefly: ignore[bad-override]
