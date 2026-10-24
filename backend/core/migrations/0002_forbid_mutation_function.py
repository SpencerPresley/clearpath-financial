from django.db import migrations


class Migration(migrations.Migration):
    """The trigger function behind `core.db.forbid_mutation`: append-only events and immutable records."""

    dependencies = [("core", "0001_postgres_extensions")]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE OR REPLACE FUNCTION core_forbid_mutation() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION '% on % is not allowed: rows are immutable', TG_OP, TG_TABLE_NAME
                        USING ERRCODE = 'restrict_violation';
                END;
                $$;
            """,
            reverse_sql="DROP FUNCTION IF EXISTS core_forbid_mutation();",
        ),
    ]
