"""LangGraph v3 protocol events -> the Agent Streaming Protocol (v2) events `@langchain/react` consumes, as SSE.

Pure: no I/O, no Django. The mapping (spike finding 4; recorded in `docs/plan/assistant.md`):

- `messages`: v3's `data = [chunk, metadata]` becomes `data = chunk` with `node = metadata["langgraph_node"]`.
- `values`: the state's messages through `message_to_wire` (other state keys are middleware bookkeeping);
  each interrupt id seen for the first time also yields one `input.requested {interrupt_id, payload}`.
- `tools`: passed through; a `tool-finished` ToolMessage output goes through `message_to_wire`, a
  `tool-error` message is replaced by a fixed line (exception text stays in the server log).
- Root `lifecycle` events don't exist in v3's log; the runner adds `running` first and one terminal event.

`seq` / `event_id` are not emitted: the client adapter numbers events per thread across runs.
"""

import json
import time
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Final, Literal, NotRequired, TypedDict

from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.stream import ProtocolEvent
from langgraph.types import StateSnapshot

from assistant.schemas import AssistantThreadStateOut

GRAPH_NAME: Final = "assistant"
KEEPALIVE: Final = b": keepalive\n\n"
TOOL_ERROR_MESSAGE: Final = "The tool failed."
_MESSAGE_KEYS: Final = ("type", "id", "content", "name", "tool_calls", "tool_call_id", "status", "artifact")

type LifecycleEvent = Literal["running", "completed", "interrupted", "failed"]


class WireParams(TypedDict):
    namespace: list[str]
    timestamp: int
    data: Any
    node: NotRequired[str | None]


class WireEvent(TypedDict):
    type: Literal["event"]
    method: str
    params: WireParams


def _now_ms() -> int:
    return int(time.time() * 1000)


def _event(method: str, namespace: list[str], data: object, *, timestamp: int | None = None) -> WireEvent:
    return {
        "type": "event",
        "method": method,
        "params": {"namespace": list(namespace), "timestamp": timestamp or _now_ms(), "data": data},
    }


def message_to_wire(message: BaseMessage) -> dict[str, Any]:
    """A message as the JS coercion reads it (`type: human | ai | tool`), without provider metadata."""
    dumped = message.model_dump()
    return {key: dumped[key] for key in _MESSAGE_KEYS if key in dumped}


def lifecycle(event: LifecycleEvent, error: str | None = None) -> WireEvent:
    data: dict[str, str] = {"event": event, "graph_name": GRAPH_NAME}
    if error is not None:
        data["error"] = error
    return _event("lifecycle", [], data)


def _messages(data: object) -> list[dict[str, Any]]:
    messages = data.get("messages", []) if isinstance(data, Mapping) else []
    return [message_to_wire(m) for m in messages if isinstance(m, BaseMessage)]


def _tools_data(data: object) -> object:
    if not isinstance(data, Mapping):
        return data
    out = dict(data)
    if out.get("event") == "tool-finished" and isinstance(out.get("output"), ToolMessage):
        out["output"] = message_to_wire(out["output"])
    elif out.get("event") == "tool-error":
        out["message"] = TOOL_ERROR_MESSAGE
    return out


def to_wire(event: ProtocolEvent, seen_interrupts: set[str]) -> list[WireEvent]:
    """The wire events for one v3 event; `seen_interrupts` carries interrupt ids already announced this run."""
    method = event["method"]
    params = event["params"]
    namespace = list(params["namespace"])
    timestamp = params["timestamp"]
    if method == "messages":
        chunk, metadata = params["data"]
        wire = _event("messages", namespace, chunk, timestamp=timestamp)
        wire["params"]["node"] = metadata.get("langgraph_node") if isinstance(metadata, Mapping) else None
        return [wire]
    if method == "values":
        out = [_event("values", namespace, {"messages": _messages(params["data"])}, timestamp=timestamp)]
        for interrupt in params.get("interrupts", ()):
            if interrupt.id in seen_interrupts:
                continue
            seen_interrupts.add(interrupt.id)
            out.append(_event("input.requested", namespace, {"interrupt_id": interrupt.id, "payload": interrupt.value}))
        return out
    if method == "tools":
        return [_event("tools", namespace, _tools_data(params["data"]), timestamp=timestamp)]
    return []


def _default(value: object) -> object:
    if isinstance(value, BaseMessage):
        return message_to_wire(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def sse_frame(event: WireEvent) -> bytes:
    data = json.dumps(event, separators=(",", ":"), ensure_ascii=False, default=_default)
    return f"event: {event['method']}\ndata: {data}\n\n".encode()


def thread_state(snapshot: StateSnapshot) -> AssistantThreadStateOut:
    """The protocol's `getState` shape: what hydrates the panel, including a pending approval."""
    values = snapshot.values if isinstance(snapshot.values, Mapping) else {}
    configurable = (snapshot.config or {}).get("configurable", {})
    checkpoint_id = configurable.get("checkpoint_id")
    metadata = snapshot.metadata
    return AssistantThreadStateOut.model_validate(
        {
            "values": {"messages": _messages(values)},
            "next": list(snapshot.next),
            "tasks": [
                {
                    "id": task.id,
                    "name": task.name,
                    "interrupts": [{"id": i.id, "value": i.value} for i in task.interrupts],
                }
                for task in snapshot.tasks
            ],
            "checkpoint": {"checkpoint_id": checkpoint_id} if checkpoint_id else None,
            "metadata": {"step": metadata.get("step")} if metadata else None,
            "created_at": snapshot.created_at,
        }
    )
