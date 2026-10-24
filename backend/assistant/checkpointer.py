"""The LangGraph Postgres checkpointer: the only store of conversation state (a thread's messages and any
pending approval). Tables come from migration `assistant/0002_checkpointer`, not from `setup()` at runtime.

One connection per run or state read, no global pool: each request (and each test) has its own event loop, and
an async psycopg connection is bound to the loop it was opened on. The checkpointer's connection is separate
from Django's, so its writes commit on their own (they outlive a test's transaction).
"""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from django.db import connection
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import make_conninfo

# Keys Django's PostgreSQL backend consumes itself; everything else in OPTIONS is passed to libpq.
_DJANGO_ONLY_OPTIONS = frozenset({"pool", "server_side_binding", "isolation_level", "assume_role", "cursor_factory"})


def postgres_conninfo(settings_dict: Mapping[str, Any] | None = None) -> str:
    """libpq conninfo for Django's default database (the test database under pytest)."""
    s = settings_dict if settings_dict is not None else connection.settings_dict
    # Django's OPTIONS mixes libpq keywords (sslmode, sslrootcert, connect_timeout, options, ...) with its own.
    options = {k: str(v) for k, v in (s.get("OPTIONS") or {}).items() if k not in _DJANGO_ONLY_OPTIONS}
    params = {
        **options,
        "dbname": s["NAME"],
        "user": s.get("USER") or None,
        "password": s.get("PASSWORD") or None,
        "host": s.get("HOST") or None,
        "port": str(s["PORT"]) if s.get("PORT") else None,
    }
    return make_conninfo(**{k: v for k, v in params.items() if v is not None})


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    async with AsyncPostgresSaver.from_conn_string(postgres_conninfo()) as saver:
        yield saver
