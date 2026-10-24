# Walkthrough S4: queue age measures from when the item last entered the queue.

from django.db import migrations, models

# Existing rows: the later of the latest (re)submission and the latest reopen. Resubmissions and new rounds already
# moved submitted_at; a reopen is the only queue entry that didn't.
BACKFILL = """
UPDATE reviews_reviewitem AS item
SET queue_entered_at = GREATEST(
    item.submitted_at,
    COALESCE(
        (SELECT MAX(e.at) FROM audit_event AS e WHERE e.item_id = item.id AND e.type = 'item.reopened'),
        item.submitted_at
    )
)
"""

QUEUE = models.Q(("status__in", ("submitted", "in_review", "needs_rereview")))


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0008_snapshot_drift"),
        ("audit", "0002_event_append_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="reviewitem",
            name="queue_entered_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.RunSQL(BACKFILL, reverse_sql=migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="reviewitem",
            name="queue_entered_at",
            field=models.DateTimeField(),
        ),
        migrations.RemoveIndex(model_name="reviewitem", name="item_queue_idx"),
        migrations.RemoveIndex(model_name="reviewitem", name="item_assignee_queue_idx"),
        migrations.AddIndex(
            model_name="reviewitem",
            index=models.Index(
                condition=QUEUE, fields=["queue_priority", "queue_entered_at", "id"], name="item_queue_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="reviewitem",
            index=models.Index(
                condition=QUEUE,
                fields=["assignee", "queue_priority", "queue_entered_at", "id"],
                name="item_assignee_queue_idx",
            ),
        ),
    ]
