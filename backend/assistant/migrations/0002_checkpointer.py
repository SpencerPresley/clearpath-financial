"""Create the LangGraph checkpointer's tables (checkpoints, checkpoint_blobs, checkpoint_writes,
checkpoint_migrations) with the library's own `setup()`.

Not atomic: the library's later migrations use CREATE INDEX CONCURRENTLY, which can't run in a transaction, so
`setup()` runs on its own autocommit psycopg connection to the same database. `setup()` is idempotent (it
records applied steps in `checkpoint_migrations`), so a library upgrade is applied by a new migration calling
it again. Reverse is a no-op: dropping conversation history is never part of rolling back code.
"""

import psycopg
from django.db import migrations
from psycopg.rows import dict_row


def create_checkpoint_tables(apps, schema_editor):
    from langgraph.checkpoint.postgres import PostgresSaver

    from assistant.checkpointer import postgres_conninfo

    conninfo = postgres_conninfo(schema_editor.connection.settings_dict)
    with psycopg.connect(conninfo, autocommit=True, prepare_threshold=0, row_factory=dict_row) as conn:
        PostgresSaver(conn).setup()


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("assistant", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_checkpoint_tables, migrations.RunPython.noop, elidable=False),
    ]
