"""Small Postgres/Django helpers shared by every app's models and migrations."""

from enum import StrEnum

from django.db import IntegrityError, migrations


def enum_choices(enum: type[StrEnum]) -> list[tuple[str, str]]:
    """Django `choices` for a `core.domain` StrEnum: value plus a readable label."""
    return [(member.value, member.value.replace("_", " ").capitalize()) for member in enum]


def constraint_name(exc: IntegrityError) -> str | None:
    """The name of the constraint an IntegrityError violated, so a service can map it to a domain error."""
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def forbid_mutation(table: str) -> migrations.RunSQL:
    """Row-level trigger making `table` insert-only (UPDATE and DELETE raise).

    Uses `core_forbid_mutation()` from core 0002. TRUNCATE is deliberately allowed: demo reset and the test
    runner's flush use it, and it's a deliberate whole-table operation rather than an edit of a record.
    """
    trigger = f"{table}_forbid_mutation"
    return migrations.RunSQL(
        sql=(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION core_forbid_mutation();"
        ),
        reverse_sql=f"DROP TRIGGER IF EXISTS {trigger} ON {table};",
    )
