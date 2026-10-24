"""The streaming endpoints end to end: scripted model, the real Postgres checkpointer, one HTTP request per
step. A run that pauses on `send_email` in one request is resumed by the next, so the approval survives in the
checkpoint and nowhere else."""

import asyncio
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from asgiref.sync import async_to_sync
from django.http import StreamingHttpResponse
from django.test import Client, override_settings
from django.utils import timezone
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from accounts.models import User
from assistant import runs
from assistant.agent import state_graph
from assistant.checkpointer import open_checkpointer
from assistant.llm import get_assistant_model
from assistant.models import AssistantThread
from assistant.tests.conftest import World
from assistant.tests.fakes import FailingModel, RecordingModel, SlowModel, scripted
from audit.models import Event
from core.domain import EventType
from notifications.models import OutboxEmail

pytestmark = pytest.mark.django_db


@dataclass(frozen=True)
class Frame:
    method: str
    data: Any  # the protocol event's params.data


@dataclass(frozen=True)
class Stream:
    frames: list[Frame]
    keepalives: int

    def methods(self) -> list[str]:
        return [f.method for f in self.frames]

    def lifecycle(self) -> list[str]:
        return [f.data["event"] for f in self.frames if f.method == "lifecycle"]

    def requested(self) -> list[dict[str, Any]]:
        return [f.data for f in self.frames if f.method == "input.requested"]


def read(response: StreamingHttpResponse) -> Stream:
    assert response.status_code == 200, response.content if not response.streaming else ""
    assert response["Content-Type"] == "text/event-stream"
    assert response["Cache-Control"] == "no-cache, no-transform"
    assert response["X-Accel-Buffering"] == "no"
    body = b"".join(response).decode()  # the sync test client drains the async iterator
    frames, keepalives = [], 0
    for block in body.split("\n\n"):
        if not block:
            continue
        if block == ": keepalive":
            keepalives += 1
            continue
        head, data = block.split("\n")
        method = head.removeprefix("event: ")
        event = json.loads(data.removeprefix("data: "))
        assert event["method"] == method
        frames.append(Frame(method=method, data=event["params"]["data"]))
    return Stream(frames=frames, keepalives=keepalives)


def _call(name: str, call_id: str, **args: Any) -> AIMessage:
    return AIMessage(content=f"Calling {name}.", tool_calls=[{"name": name, "args": args, "id": call_id}])


class Panel:
    """One user's panel: a logged-in client and a thread."""

    def __init__(self, user: User) -> None:
        self.user = user
        self.client = Client()
        self.client.force_login(user)
        response = self.client.post("/api/assistant/threads")
        assert response.status_code == 201
        self.thread_id = UUID(response.json()["id"])

    @property
    def base(self) -> str:
        return f"/api/assistant/threads/{self.thread_id}"

    def send(self, content: str, *, message_id: str = "u1", item_id: int | None = None) -> Any:
        body: dict[str, Any] = {"message": {"id": message_id, "content": content}}
        if item_id is not None:
            body["item_id"] = item_id
        return self.client.post(f"{self.base}/runs", body, content_type="application/json")

    def respond(self, interrupt_id: str, answer: dict[str, Any]) -> Any:
        return self.client.post(f"{self.base}/interrupts/{interrupt_id}", answer, content_type="application/json")

    def state(self) -> dict[str, Any]:
        response = self.client.get(f"{self.base}/state")
        assert response.status_code == 200
        return response.json()

    def thread(self) -> AssistantThread:
        return AssistantThread.objects.get(pk=self.thread_id)


def use_models(monkeypatch: pytest.MonkeyPatch, *models: BaseChatModel) -> None:
    """Each run (request) builds its model through the factory: hand out these in order."""
    pending = list(models)
    factory: Callable[[], BaseChatModel] = lambda: pending.pop(0)  # noqa: E731
    monkeypatch.setattr(runs, "MODEL_FACTORY", factory)


def _draft_script(world: World) -> BaseChatModel:
    return scripted(
        _call("search_items", "c1", assigned_to_me=True),
        _call("get_item", "c2", item_key=world.item.key),
        _call(
            "send_email",
            "c3",
            to=["dana@clearpath.demo"],
            subject="Findings",
            body="One open finding.",
            item_key=world.item.key,
        ),
        "Sent it to Dana.",
    )


def _pause(panel: Panel, world: World, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run until the draft awaits approval; returns the interrupt id."""
    use_models(monkeypatch, _draft_script(world))
    stream = read(panel.send("Email Dana the findings on my item"))
    (requested,) = stream.requested()
    return requested["interrupt_id"]


def test_search_read_draft_pauses_then_approve_sends_once(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    model = _draft_script(world)
    use_models(monkeypatch, model, model)  # the resume continues the same script

    first = read(panel.send("  Email Dana\n the findings on my item  "))

    assert first.frames[0].method == "lifecycle"
    assert first.lifecycle() == ["running", "interrupted"]
    tools = [f.data for f in first.frames if f.method == "tools" and f.data["event"] == "tool-finished"]
    assert [t["output"]["name"] for t in tools] == ["search_items", "get_item"]
    assert tools[1]["output"]["artifact"] == {"item_keys": [world.item.key]}
    assert any(f.method == "messages" and f.data["event"] == "content-block-delta" for f in first.frames)
    (requested,) = first.requested()
    assert requested["payload"]["type"] == "tool_approval"
    assert requested["payload"]["args"]["to"] == ["dana@clearpath.demo"]
    interrupt_id = requested["interrupt_id"]
    thread = panel.thread()
    assert (thread.awaiting_approval, thread.running_since, thread.title) == (
        True,
        None,
        "Email Dana the findings on my item",
    )
    assert not OutboxEmail.objects.exists()

    # A reload: the pending approval comes back from the checkpoint (a separate connection).
    state = panel.state()
    assert state["next"] == ["tools"]
    (task,) = state["tasks"]
    assert [i["id"] for i in task["interrupts"]] == [interrupt_id]
    assert task["interrupts"][0]["value"]["args"]["subject"] == "Findings"
    assert [m["type"] for m in state["values"]["messages"]] == ["human", "ai", "tool", "ai", "tool", "ai"]
    assert state["checkpoint"]["checkpoint_id"]

    blocked = panel.send("Never mind, what else is waiting?", message_id="u2")
    assert blocked.status_code == 409
    assert "waiting for your approval" in blocked.json()["message"]

    second = read(panel.respond(interrupt_id, {"type": "approve", "interruptId": interrupt_id}))

    assert second.lifecycle() == ["running", "completed"]
    assert second.requested() == []
    email = OutboxEmail.objects.get()
    sent = {"outcome": "sent", "outbox_id": email.pk, "to": ["dana@clearpath.demo"], "item_keys": [world.item.key]}
    (finished,) = [
        f.data for f in second.frames if f.method == "tools" and f.data["event"] == "tool-finished"
    ]  # the tools event carries it...
    assert finished["output"]["artifact"] == sent
    values = [f.data for f in second.frames if f.method == "values"][-1]["messages"]
    assert [m["artifact"] for m in values if m.get("tool_call_id") == "c3"] == [sent]  # ...and so do values
    assert [m["artifact"] for m in panel.state()["values"]["messages"] if m.get("tool_call_id") == "c3"] == [sent]
    assert (email.to, email.requested_by, email.approved_by) == (
        ["dana@clearpath.demo"],
        world.reviewer,
        world.reviewer,
    )
    assert email.thread_id == str(panel.thread_id)
    assert Event.objects.filter(type=EventType.EMAIL_SENT, entity_id=email.pk).count() == 1
    assert panel.thread().awaiting_approval is False
    final = panel.state()
    assert final["next"] == []
    assert final["tasks"] == []
    assert final["values"]["messages"][-1]["content"][0]["text"] == "Sent it to Dana."  # v1 content blocks

    again = panel.respond(interrupt_id, {"type": "approve"})
    assert again.status_code == 409
    assert again.json()["message"] == "That approval is no longer pending."
    assert OutboxEmail.objects.count() == 1


def test_reject_sends_nothing_and_tells_the_model(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    interrupt_id = _pause(panel, world, monkeypatch)
    use_models(monkeypatch, scripted("Okay, I won't send it."))

    stream = read(panel.respond(interrupt_id, {"type": "reject"}))

    assert stream.lifecycle() == ["running", "completed"]
    assert not OutboxEmail.objects.exists()
    tool = [m for m in panel.state()["values"]["messages"] if m["type"] == "tool"][-1]
    assert tool["status"] == "error"
    assert runs.REJECT_DEFAULT in tool["content"]
    declined = {"outcome": "declined", "to": ["dana@clearpath.demo"], "item_keys": [world.item.key]}
    assert tool["artifact"] == declined
    values = [f.data for f in stream.frames if f.method == "values"][-1]["messages"]
    assert [m["artifact"] for m in values if m.get("tool_call_id") == "c3"] == [declined]
    assert not [f for f in stream.frames if f.method == "tools" and f.data.get("tool_call_id") == "c3"]


def test_edit_to_an_outside_address_is_a_field_error(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    interrupt_id = _pause(panel, world, monkeypatch)
    args = {"to": ["dana@clearpath.demo", "partner@evil.example"], "subject": "Findings", "body": "Here."}

    response = panel.respond(interrupt_id, {"type": "edit", "edited_action": {"name": "send_email", "args": args}})

    assert response.status_code == 422
    (field,) = response.json()["fields"]
    assert field["loc"] == ["body", "to"]
    assert "partner@evil.example" in field["message"]
    assert not OutboxEmail.objects.exists()
    assert panel.thread().running_since is None
    assert [t["interrupts"][0]["id"] for t in panel.state()["tasks"]] == [interrupt_id]  # still answerable


def test_edit_sends_the_edited_draft(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    interrupt_id = _pause(panel, world, monkeypatch)
    use_models(monkeypatch, scripted("Sent to compliance."))
    args = {"to": ["Compliance@clearpath.demo"], "subject": "Edited", "body": "Edited body.", "item_key": None}

    stream = read(panel.respond(interrupt_id, {"type": "edit", "edited_action": {"name": "send_email", "args": args}}))

    assert stream.lifecycle() == ["running", "completed"]
    email = OutboxEmail.objects.get()
    assert (email.to, email.subject, email.item) == (["compliance@clearpath.demo"], "Edited", None)


def test_a_second_run_on_a_busy_thread_is_refused(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    AssistantThread.objects.filter(pk=panel.thread_id).update(running_since=timezone.now())

    busy = panel.send("hi")

    assert busy.status_code == 409
    assert busy.json()["message"] == "A reply is already running in this thread."

    # A lock left by a process that died is taken over once it's stale.
    AssistantThread.objects.filter(pk=panel.thread_id).update(running_since=timezone.now() - timedelta(minutes=11))
    use_models(monkeypatch, scripted("Hello."))
    assert read(panel.send("hi")).lifecycle() == ["running", "completed"]


def test_another_users_thread_is_not_found_on_every_route(world: World, marketer: User) -> None:
    panel = Panel(world.reviewer)
    other = Client()
    other.force_login(world.marketer)

    assert other.get(f"{panel.base}/state").status_code == 404
    run = other.post(f"{panel.base}/runs", {"message": {"id": "u1", "content": "hi"}}, content_type="application/json")
    assert run.status_code == 404
    resume = other.post(f"{panel.base}/interrupts/abc", {"type": "approve"}, content_type="application/json")
    assert resume.status_code == 404


def test_new_thread_state_is_empty(owner: User) -> None:
    assert Panel(owner).state() == {
        "values": {"messages": []},
        "next": [],
        "tasks": [],
        "checkpoint": None,
        "metadata": None,
        "created_at": None,
    }


def test_unknown_open_item_is_not_found(owner: User) -> None:
    response = Panel(owner).send("What about this one?", item_id=999_999)
    assert response.status_code == 404


def test_open_item_run(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    use_models(monkeypatch, scripted(_call("get_item", "c1", item_key=world.item.key), "It has one open finding."))

    stream = read(panel.send("What's open on this one?", item_id=world.item.pk))

    assert stream.lifecycle() == ["running", "completed"]


def test_model_failure_is_one_line_and_the_thread_stays_usable(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    use_models(monkeypatch, FailingModel(), scripted("Back."))

    failed = read(panel.send("hi"))

    assert failed.lifecycle() == ["running", "failed"]
    error = failed.frames[-1].data["error"]
    assert error == "Something went wrong running the assistant. Try again."
    assert "req_secret" not in json.dumps([f.data for f in failed.frames])
    assert panel.thread().running_since is None

    retried = read(panel.send("hi again", message_id="u2"))
    assert retried.lifecycle() == ["running", "completed"]


@override_settings(ASSISTANT_ANTHROPIC_API_KEY=None)
def test_missing_api_key_fails_the_stream_not_the_request(owner: User, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runs, "MODEL_FACTORY", get_assistant_model)

    stream = read(Panel(owner).send("hi"))

    assert stream.lifecycle() == ["running", "failed"]
    assert stream.frames[-1].data["error"] == "The assistant isn't configured (no API key)."


def test_keepalive_while_the_model_is_slow(owner: User, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runs, "KEEPALIVE_SECONDS", 0.05)
    use_models(monkeypatch, SlowModel(messages=iter(["Done thinking."]), delay=0.3))

    stream = read(Panel(owner).send("hi"))

    assert stream.keepalives >= 2
    assert stream.lifecycle() == ["running", "completed"]


def _cut_short(panel: Panel, item_key: str) -> tuple[str, ...]:
    """Checkpoint a run that stopped after the model asked for a tool and before the tool's result was saved
    (what a disconnect mid-tool leaves). Returns the checkpoint's `next`."""

    async def write() -> tuple[str, ...]:
        config: Any = {"configurable": {"thread_id": str(panel.thread_id)}}
        async with open_checkpointer() as saver:
            graph = state_graph(viewer=panel.user, checkpointer=saver)
            call = {"name": "get_item", "args": {"item_key": item_key}, "id": "c9"}
            messages = [HumanMessage("Look up my item", id="u0"), AIMessage(content="", id="a0", tool_calls=[call])]
            await graph.aupdate_state(config, {"messages": messages}, as_node="model")
            return (await graph.aget_state(config)).next

    return async_to_sync(write)()


def test_a_run_cut_short_mid_tool_gets_its_tool_result_before_the_next_message(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = Panel(world.reviewer)
    assert _cut_short(panel, world.item.key)  # the dead run left a step to do and no interrupt
    model = RecordingModel(messages=iter(["Back again."]))
    use_models(monkeypatch, model)

    stream = read(panel.send("Are you there?", message_id="u1"))

    assert stream.lifecycle() == ["running", "completed"]
    (request,) = model.requests
    assert [m.type for m in request] == ["system", "human", "ai", "tool", "human"]
    stopped = request[3]
    assert isinstance(stopped, ToolMessage)
    assert (stopped.tool_call_id, stopped.name, stopped.status) == ("c9", "get_item", "error")
    assert stopped.content == '{"error":"Stopped before it finished."}'


def test_state_of_a_dead_run_has_nothing_next(world: World) -> None:
    panel = Panel(world.reviewer)
    assert _cut_short(panel, world.item.key)

    state = panel.state()

    assert state["next"] == []
    assert [m["type"] for m in state["values"]["messages"]] == ["human", "ai"]

    # While a request holds a fresh lock the run is alive, and its next step is real.
    AssistantThread.objects.filter(pk=panel.thread_id).update(running_since=timezone.now())
    assert panel.state()["next"] != []


def test_history_is_owner_checked_and_empty(world: World) -> None:
    panel = Panel(world.reviewer)
    url = f"{panel.base}/history"

    response = panel.client.post(url, {"limit": 20, "before": None}, content_type="application/json")
    assert response.status_code == 200
    assert response.json() == []
    assert panel.client.post(url, {}, content_type="application/json").json() == []
    assert panel.client.post(url, {"limit": 500}, content_type="application/json").status_code == 422

    other = Client()
    other.force_login(world.marketer)
    assert other.post(url, {"limit": 20}, content_type="application/json").status_code == 404


@pytest.mark.parametrize("subject", ["Findings\r\nBcc: partner@evil.example", "Two\nlines"])
def test_edit_with_a_multi_line_subject_is_a_field_error(
    world: World, monkeypatch: pytest.MonkeyPatch, subject: str
) -> None:
    panel = Panel(world.reviewer)
    interrupt_id = _pause(panel, world, monkeypatch)
    args = {"to": ["dana@clearpath.demo"], "subject": subject, "body": "Here."}

    response = panel.respond(interrupt_id, {"type": "edit", "edited_action": {"name": "send_email", "args": args}})

    assert response.status_code == 422
    (field,) = response.json()["fields"]
    assert field["loc"][-1] == "subject"
    assert "one line" in field["message"]
    assert not OutboxEmail.objects.exists()


def test_edit_with_an_unknown_item_key_is_a_field_error(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    interrupt_id = _pause(panel, world, monkeypatch)
    args = {"to": ["dana@clearpath.demo"], "subject": "s", "body": "b", "item_key": "CP-999999"}

    response = panel.respond(interrupt_id, {"type": "edit", "edited_action": {"name": "send_email", "args": args}})

    assert response.status_code == 422
    assert response.json()["fields"][0]["loc"] == ["body", "item_key"]


def test_disconnect_while_the_approved_send_runs_never_sends_twice(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ASGI smoke failure: the client leaves while `send_email` is executing. The email commits (sync code
    can't be cancelled), but the tools step is cancelled before its checkpoint, so the approval still shows as
    pending. Approving again must not send a second email: the send is idempotent per tool call."""
    panel = Panel(world.reviewer)
    interrupt_id = _cut_send_short(panel, world, monkeypatch)
    use_models(monkeypatch, scripted("Sent it to Dana."))

    # The step was cut short: the card is back, and Approve finishes the run without a resend.
    assert panel.thread().running_since is None
    assert panel.thread().awaiting_approval is True
    assert read(panel.respond(interrupt_id, {"type": "approve"})).lifecycle() == ["running", "completed"]

    assert OutboxEmail.objects.count() == 1
    assert Event.objects.filter(type=EventType.EMAIL_SENT).count() == 1
    assert panel.state()["tasks"] == []
    assert panel.thread().awaiting_approval is False


def test_subject_with_a_newline_is_rejected_in_the_run_input_schema() -> None:
    from pydantic import ValidationError

    from assistant.schemas import EmailDraftIn

    with pytest.raises(ValidationError, match="Subject must be one line"):
        EmailDraftIn(to=["dana@clearpath.demo"], subject="a\rb", body="b")


def test_blocked_send_outcome_on_the_wire_and_in_state(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    panel = Panel(world.reviewer)
    to = ["partner@evil.example"]
    use_models(
        monkeypatch, scripted(_call("send_email", "c1", to=to, subject="s", body="b"), "That address isn't allowed.")
    )

    stream = read(panel.send("Email the partner"))

    assert stream.lifecycle() == ["running", "completed"]
    assert stream.requested() == []
    (tool,) = [m for m in panel.state()["values"]["messages"] if m["type"] == "tool"]
    assert tool["artifact"] == {
        "outcome": "blocked",
        "refused": to,
        "reason": tool["content"],
        "to": to,
        "item_keys": [],
    }
    values = [f.data for f in stream.frames if f.method == "values"][-1]["messages"]
    assert [m["artifact"] for m in values if m["type"] == "tool"] == [tool["artifact"]]


def _approve_and_leave(
    panel: Panel,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    *,
    leave: threading.Event,
    arm: Callable[[], Callable[[], None]],
) -> str:
    """Pause on the draft to dana@, approve, and disconnect once `leave` is set (by a step `arm` patches in,
    at the exact point the test is about). `arm` runs after the pause, so only the approved run is patched, and
    returns the undo. Returns the interrupt id."""
    interrupt_id = _pause(panel, world, monkeypatch)
    token = runs.services.claim_run(thread_id=panel.thread_id, owner=world.reviewer)
    disarm = arm()

    async def approve_then_leave() -> None:
        stream = runs.stream_run(
            thread_id=panel.thread_id,
            viewer=world.reviewer,
            command=runs.Resume(interrupt_id=interrupt_id, decision={"type": "approve"}),
            token=token,
            model_factory=lambda: scripted("Sent."),
        )
        await anext(stream)  # the run is under way
        assert await asyncio.to_thread(leave.wait, 10), "the run never reached the point the test leaves at"
        await stream.aclose()

    async_to_sync(approve_then_leave)()
    disarm()
    return interrupt_id


def _swap(module: Any, name: str, value: Any) -> Callable[[], Callable[[], None]]:
    """An `arm` for `_approve_and_leave`: put `value` at `module.name`, and return how to put it back."""

    def arm() -> Callable[[], None]:
        original = getattr(module, name)
        setattr(module, name, value)
        return lambda: setattr(module, name, original)

    return arm


def _held_until_the_run_is_cut(monkeypatch: pytest.MonkeyPatch) -> threading.Event:
    """Set once the run has been cancelled: `stream_run` reads the checkpoint's pending approvals only after
    stopping a cut-short run. A send held on this is still executing when the cancel lands."""
    cut = threading.Event()
    pending = runs.pending_interrupt_ids

    async def mark_then_read(**kwargs: Any) -> set[str]:
        cut.set()
        return await pending(**kwargs)

    monkeypatch.setattr(runs, "pending_interrupt_ids", mark_then_read)
    return cut


def _cut_send_short(panel: Panel, world: World, monkeypatch: pytest.MonkeyPatch) -> str:
    """Approve, let the email commit, and disconnect while the send is still inside the tool: the email is in the
    Outbox but the step never checkpointed, so the approval is pending again. Returns the interrupt id."""
    from assistant import tools

    real = tools.send_approved_email
    stored = threading.Event()
    cut = _held_until_the_run_is_cut(monkeypatch)

    def send_then_hold(**kwargs: Any) -> Any:
        sent = real(**kwargs)
        stored.set()  # committed: send_approved_email's transaction has closed
        assert cut.wait(10), "the run was never cut short"
        return sent

    interrupt_id = _approve_and_leave(
        panel, world, monkeypatch, leave=stored, arm=_swap(tools, "send_approved_email", send_then_hold)
    )
    assert OutboxEmail.objects.count() == 1
    assert [i["id"] for t in panel.state()["tasks"] for i in t["interrupts"]] == [interrupt_id]  # the card is back
    return interrupt_id


def test_a_disconnect_before_the_send_starts_sends_nothing_and_shows_the_card_again(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side of a cut-short send (and the ordering that made CI flaky): the client leaves after
    `tool-started` but before the send's sync work begins. The cancel stops it from ever running, so nothing is
    stored or recorded, and the user answers the same card again."""
    from assistant import tools

    real = tools.sync_to_async
    parked = threading.Event()

    def park_first(fn: Any, *args: Any, **kwargs: Any) -> Any:  # wraps sync_to_async
        inner = real(fn, *args, **kwargs)

        async def go(*a: Any, **kw: Any) -> Any:
            parked.set()
            await asyncio.Event().wait()  # until the run is cancelled
            return await inner(*a, **kw)

        return go

    panel = Panel(world.reviewer)
    interrupt_id = _approve_and_leave(
        panel, world, monkeypatch, leave=parked, arm=_swap(tools, "sync_to_async", park_first)
    )

    assert OutboxEmail.objects.count() == 0
    assert not Event.objects.filter(type=EventType.EMAIL_SENT).exists()
    assert panel.thread().running_since is None
    assert panel.thread().awaiting_approval is True
    assert [i["id"] for t in panel.state()["tasks"] for i in t["interrupts"]] == [interrupt_id]

    use_models(monkeypatch, scripted("Sent it to Dana."))
    assert read(panel.respond(interrupt_id, {"type": "approve"})).lifecycle() == ["running", "completed"]
    assert list(OutboxEmail.objects.values_list("to", flat=True)) == [["dana@clearpath.demo"]]
    assert Event.objects.filter(type=EventType.EMAIL_SENT).count() == 1


def test_a_disconnect_mid_send_still_commits_the_whole_send_before_the_thread_is_released(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cancel lands while the send is executing but before it has written anything. Sync code can't be
    interrupted, and the lease release is queued behind it on the same thread, so by the time the thread is free
    the email and its EMAIL_SENT event are both committed: never half-sent, never sent after the run let go."""
    from assistant import tools

    real = tools.send_approved_email
    started = threading.Event()
    cut = _held_until_the_run_is_cut(monkeypatch)

    held_at_commit: list[bool] = []

    def hold_then_send(**kwargs: Any) -> Any:
        started.set()
        assert cut.wait(10), "the run was never cut short"
        sent = real(**kwargs)
        held_at_commit.append(AssistantThread.objects.get(pk=panel.thread_id).running_since is not None)
        return sent

    panel = Panel(world.reviewer)
    interrupt_id = _approve_and_leave(
        panel, world, monkeypatch, leave=started, arm=_swap(tools, "send_approved_email", hold_then_send)
    )

    assert held_at_commit == [True]  # the run still held the thread when the email committed
    assert panel.thread().running_since is None
    assert OutboxEmail.objects.count() == 1
    assert Event.objects.filter(type=EventType.EMAIL_SENT).count() == 1
    assert [i["id"] for t in panel.state()["tasks"] for i in t["interrupts"]] == [interrupt_id]


@pytest.mark.parametrize(
    "answer",
    [
        {"type": "reject", "message": "Not now"},
        {
            "type": "edit",
            "edited_action": {
                "name": "send_email",
                "args": {"to": ["compliance@clearpath.demo"], "subject": "Other", "body": "Other body."},
            },
        },
        {"type": "approve"},
    ],
    ids=["reject", "edit", "approve"],
)
def test_any_answer_after_a_cut_short_send_reports_the_stored_email(
    world: World, monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any]
) -> None:
    panel = Panel(world.reviewer)
    interrupt_id = _cut_send_short(panel, world, monkeypatch)
    use_models(monkeypatch, scripted("Already sent to Dana."))

    stream = read(panel.respond(interrupt_id, answer))

    assert stream.lifecycle() == ["running", "completed"]
    email = OutboxEmail.objects.get()
    assert email.to == ["dana@clearpath.demo"]
    assert Event.objects.filter(type=EventType.EMAIL_SENT).count() == 1
    (tool,) = [m for m in panel.state()["values"]["messages"] if m.get("tool_call_id") == "c3"]
    assert tool["artifact"] == {
        "outcome": "sent",
        "outbox_id": email.pk,
        "to": ["dana@clearpath.demo"],
        "item_keys": [world.item.key],
    }
    assert json.loads(tool["content"])["to"] == ["dana@clearpath.demo"]
    assert panel.state()["tasks"] == []
    assert panel.thread().awaiting_approval is False


def test_history_skips_csrf_but_runs_dont(world: World) -> None:
    panel = Panel(world.reviewer)
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(world.reviewer)

    history = strict.post(f"{panel.base}/history", {"limit": 20}, content_type="application/json")
    run = strict.post(f"{panel.base}/runs", {"message": {"id": "u1", "content": "hi"}}, content_type="application/json")

    assert history.status_code == 200
    assert run.status_code == 403
    assert (
        Client(enforce_csrf_checks=True).post(f"{panel.base}/history", {}, content_type="application/json").status_code
        == 401
    )


def test_declined_outcome_doesnt_depend_on_the_librarys_reject_wording(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from langchain.agents.middleware import human_in_the_loop
    from langchain_core.messages import ToolMessage as LCToolMessage

    def reworded(tool_call: Any, decision: Any) -> LCToolMessage:
        return LCToolMessage(
            content=f"Rejected by reviewer. Note: {decision.get('message', '')}",
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
            status="error",
        )

    panel = Panel(world.reviewer)
    interrupt_id = _pause(panel, world, monkeypatch)
    monkeypatch.setattr(human_in_the_loop, "_answer_message", reworded)
    use_models(monkeypatch, scripted("Okay."))

    read(panel.respond(interrupt_id, {"type": "reject", "message": "Wrong person"}))

    (tool,) = [m for m in panel.state()["values"]["messages"] if m.get("tool_call_id") == "c3"]
    assert tool["artifact"]["outcome"] == "declined"
    assert "Their reason: Wrong person" in tool["content"]
