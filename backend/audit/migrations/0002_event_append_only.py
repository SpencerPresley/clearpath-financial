from django.db import migrations

from core.db import forbid_mutation


class Migration(migrations.Migration):
    """The audit trail is append-only: nothing updates or deletes an event (CLAUDE.md invariants)."""

    dependencies = [
        ("audit", "0001_initial"),
        ("core", "0002_forbid_mutation_function"),
    ]

    operations = [forbid_mutation("audit_event")]
