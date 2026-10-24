from django.db import migrations


def _same_item(table: str, name: str, version_column: str, item_column: str) -> migrations.RunSQL:
    """Composite FK: `table.version_column` must be a version of the item in `table.item_column`.

    Django has no composite foreign keys, so these live in SQL. MATCH SIMPLE (the default) skips rows whose
    version column is null, which is what `ReviewItem.current_version` needs before its first version.
    """
    return migrations.RunSQL(
        sql=(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({version_column}, {item_column}) "
            "REFERENCES reviews_version (id, item_id);"
        ),
        reverse_sql=f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};",
    )


class Migration(migrations.Migration):
    """A decision, a placement, and an item's current version must all point at a version of the same item.

    The single-column FKs only prove the version exists; without these, a service bug could approve CP-7
    against CP-9's text and the record would say so forever (decisions and versions are immutable).
    """

    dependencies = [("reviews", "0005_queue_priority_trgm_version_key")]

    operations = [
        _same_item("reviews_decision", "decision_version_same_item", "version_id", "item_id"),
        _same_item("reviews_placement", "placement_version_same_item", "approved_version_id", "item_id"),
        _same_item("reviews_reviewitem", "item_current_version_same_item", "current_version_id", "id"),
    ]
