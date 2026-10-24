from django.contrib.postgres.operations import BtreeGistExtension, TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Extensions the domain schema depends on.

    btree_gist backs the EXCLUDE constraint that keeps offer-terms effective
    ranges from overlapping; pg_trgm backs fuzzy title and phrase search.
    """

    initial = True
    dependencies: list[tuple[str, str]] = []

    operations = [
        BtreeGistExtension(),
        TrigramExtension(),
    ]
