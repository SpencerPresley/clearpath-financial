"""`to_wire`, one test per mapping (pure: no DB, no graph)."""

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.stream import ProtocolEvent
from langgraph.types import Interrupt, StateSnapshot

from assistant.wire import KEEPALIVE, lifecycle, message_to_wire, sse_frame, thread_state, to_wire


def _event(method: str, data: Any, **extra: Any) -> ProtocolEvent:
    event: ProtocolEvent = {
        "type": "event",
        "method": method,
        "params": {"namespace": [], "timestamp": 1, "data": data},
    }
    if "interrupts" in extra:
        event["params"]["interrupts"] = extra["interrupts"]
    return event


AI = AIMessage(
    content=[{"type": "text", "text": "Looking."}, {"type": "tool_call", "id": "c1", "name": "get_item", "args": {}}],
    id="a1",
    tool_calls=[{"name": "get_item", "args": {"item_key": "CP-1"}, "id": "c1"}],
    response_metadata={"model_name": "claude-haiku-5-5", "stop_reason": "tool_use"},
    additional_kwargs={"x": 1},
    usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
)
TOOL = ToolMessage(content='{"key":"CP-1"}', tool_call_id="c1", name="get_item", artifact={"item_keys": ["CP-1"]})
APPROVAL = {"type": "tool_approval", "tool_call_id": "c3", "name": "send_email", "args": {"to": ["a@x"]}}


def test_lifecycle_events() -> None:
    running = lifecycle("running")
    assert running["method"] == "lifecycle"
    assert running["params"]["namespace"] == []
    assert running["params"]["data"] == {"event": "running", "graph_name": "assistant"}
    assert lifecycle("failed", "One line.")["params"]["data"]["error"] == "One line."


def test_messages_unwrap_chunk_and_node() -> None:
    chunk = {"event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": "Hi"}}

    (wire,) = to_wire(_event("messages", [chunk, {"langgraph_node": "model", "ls_provider": "anthropic"}]), set())

    assert wire["params"] == {"namespace": [], "timestamp": 1, "data": chunk, "node": "model"}


def test_message_to_wire_drops_provider_metadata() -> None:
    wired = message_to_wire(AI)

    assert set(wired) == {"type", "id", "content", "name", "tool_calls"}
    assert wired["type"] == "ai"
    assert wired["tool_calls"][0]["args"] == {"item_key": "CP-1"}
    assert message_to_wire(TOOL) == {
        "type": "tool",
        "id": None,
        "content": '{"key":"CP-1"}',
        "name": "get_item",
        "tool_call_id": "c1",
        "status": "success",
        "artifact": {"item_keys": ["CP-1"]},
    }
    assert message_to_wire(HumanMessage("hi", id="u1")) == {"type": "human", "id": "u1", "content": "hi", "name": None}


def test_values_carry_only_messages() -> None:
    state = {"messages": [HumanMessage("hi", id="u1"), AI], "run_model_call_count": 1, "jump_to": None}

    (wire,) = to_wire(_event("values", state), set())

    assert wire["method"] == "values"
    assert [m["type"] for m in wire["params"]["data"]["messages"]] == ["human", "ai"]
    assert set(wire["params"]["data"]) == {"messages"}


def test_each_new_interrupt_is_requested_once() -> None:
    seen: set[str] = set()
    interrupt = Interrupt(value=APPROVAL, id="i1")

    first = to_wire(_event("values", {"messages": []}, interrupts=(interrupt,)), seen)
    again = to_wire(_event("values", {"messages": []}, interrupts=(interrupt,)), seen)

    assert [w["method"] for w in first] == ["values", "input.requested"]
    assert first[1]["params"]["data"] == {"interrupt_id": "i1", "payload": APPROVAL}
    assert first[1]["params"]["namespace"] == []
    assert [w["method"] for w in again] == ["values"]


def test_tools_events() -> None:
    started = {"event": "tool-started", "tool_call_id": "c1", "tool_name": "get_item", "input": {"item_key": "CP-1"}}
    finished = {"event": "tool-finished", "tool_call_id": "c1", "output": TOOL}
    failed = {"event": "tool-error", "tool_call_id": "c1", "message": "psycopg.OperationalError: host db:5432"}

    assert to_wire(_event("tools", started), set())[0]["params"]["data"] == started
    assert to_wire(_event("tools", finished), set())[0]["params"]["data"]["output"] == message_to_wire(TOOL)
    assert to_wire(_event("tools", failed), set())[0]["params"]["data"]["message"] == "The tool failed."


def test_other_methods_are_dropped() -> None:
    assert to_wire(_event("updates", {"model": {}}), set()) == []
    assert to_wire(_event("checkpoints", {}), set()) == []


def test_sse_frame() -> None:
    event = to_wire(_event("values", {"messages": [HumanMessage("Résumé\nline two", id="u1")]}), set())[0]

    frame = sse_frame(event)

    head, data = frame.decode().removesuffix("\n\n").split("\n")
    assert head == "event: values"
    assert data.startswith('data: {"type":"event","method":"values","params":{')
    assert "Résumé\\nline two" in data
    assert json.loads(data.removeprefix("data: ")) == json.loads(json.dumps(event))
    assert "seq" not in data
    assert KEEPALIVE == b": keepalive\n\n"


def test_state_of_an_empty_thread() -> None:
    snapshot = StateSnapshot(
        values={},
        next=(),
        config={"configurable": {"thread_id": "t"}},
        metadata=None,
        created_at=None,
        parent_config=None,
        tasks=(),
        interrupts=(),
    )

    state = thread_state(snapshot)

    assert state.model_dump() == {
        "values": {"messages": []},
        "next": [],
        "tasks": [],
        "checkpoint": None,
        "metadata": None,
        "created_at": None,
    }
