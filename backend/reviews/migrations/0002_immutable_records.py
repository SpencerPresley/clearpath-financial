from django.db import migrations

from core.db import forbid_mutation


class Migration(migrations.Migration):
    """Versions, decisions, and evidence are records: once written, never edited or deleted (spec §4.1)."""

    dependencies = [("reviews", "0001_initial")]

    operations = [
        forbid_mutation("reviews_version"),
        forbid_mutation("reviews_decision"),
        forbid_mutation("reviews_decisiontermsversion"),
        forbid_mutation("reviews_decisionevidence"),
        forbid_mutation("reviews_attachment"),
    ]
