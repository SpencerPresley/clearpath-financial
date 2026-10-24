import uuid

import pytest
from asgiref.sync import async_to_sync
from django.db import connection
from langchain_core.messages import HumanMessage
from langgraph.graph import START, MessagesState, StateGraph

from assistant.checkpointer import open_checkpointer, postgres_conninfo


@pytest.mark.django_db
def test_checkpointer_tables_exist() -> None:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT to_regclass('checkpoints'), to_regclass('checkpoint_writes'), to_regclass('checkpoint_blobs')"
        )
        assert all(cur.fetchone())


@pytest.mark.django_db
def test_conninfo_points_at_the_test_database() -> None:
    assert f"dbname={connection.settings_dict['NAME']}" in postgres_conninfo()
    assert connection.settings_dict["NAME"].startswith("test_")


def _noop(state: MessagesState) -> dict:
    return {}


@pytest.mark.django_db
def test_checkpointer_round_trips_a_thread() -> None:
    graph = StateGraph(MessagesState)  # pyrefly: ignore[bad-specialization]  # TypedDict state is supported
    graph.add_node("noop", _noop)
    graph.add_edge(START, "noop")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async def run() -> list[str]:
        async with open_checkpointer() as saver:
            compiled = graph.compile(checkpointer=saver)
            await compiled.ainvoke({"messages": [HumanMessage("hi", id="m1")]}, config)
        async with open_checkpointer() as saver:  # a fresh connection, as the next request would open
            state = await graph.compile(checkpointer=saver).aget_state(config)
        return [m.id for m in state.values["messages"]]

    assert async_to_sync(run)() == ["m1"]


def test_conninfo_carries_libpq_options_but_not_djangos() -> None:
    settings_dict = {
        "NAME": "clearpath",
        "USER": "u",
        "PASSWORD": "p",
        "HOST": "db",
        "PORT": 5432,
        "OPTIONS": {"sslmode": "require", "connect_timeout": 5, "pool": True, "server_side_binding": False},
    }

    conninfo = postgres_conninfo(settings_dict)

    assert "sslmode=require" in conninfo
    assert "connect_timeout=5" in conninfo
    assert "pool" not in conninfo
    assert "server_side_binding" not in conninfo
