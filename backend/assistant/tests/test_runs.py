import asyncio
import logging
import time
import uuid
from collections.abc import Sequence

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.http import StreamingHttpResponse
from langgraph.checkpoint.memory import InMemorySaver

from accounts.models import User
from assistant import runs, services
from assistant.models import AssistantThread
from assistant.tests.fakes import SlowModel, scripted
from core.clock import FixedClock
from core.errors import Conflict


@pytest.mark.django_db
def test_closing_the_stream_aborts_the_run_and_releases_the_lock(owner: User, clock: FixedClock) -> None:
    thread = services.create_thread(owner=owner, clock=clock)
    token = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)
    saver = InMemorySaver()

    class _Saver:
        async def __aenter__(self) -> InMemorySaver:
            return saver

        async def __aexit__(self, *exc: object) -> None:
            return None

    async def disconnect_mid_run() -> list[bytes]:
        stream = runs.stream_run(
            thread_id=thread.pk,
            viewer=owner,
            command=runs.StartRun(message_id="u1", content="hi"),
            token=token,
            model_factory=lambda: SlowModel(messages=iter(["Never finishes."]), delay=2),
            checkpointer_factory=_Saver,
            clock=clock,
        )
        frames = [await anext(stream)]
        while not frames[-1].startswith(b"event: values"):  # the run is going; the model is "thinking"
            frames.append(await anext(stream))
        await stream.aclose()  # what Django does when the client goes away
        return frames

    started = time.monotonic()
    frames = async_to_sync(disconnect_mid_run)()

    assert time.monotonic() - started < 1.5  # didn't wait for the model
    assert frames[0].startswith(b"event: lifecycle\n")
    assert not any(b'"completed"' in f or b'"failed"' in f for f in frames)
    thread.refresh_from_db()
    assert thread.running_since is None
    assert thread.title == "hi"


@pytest.mark.django_db
def test_release_leaves_a_taken_over_lock_alone(owner: User, clock: FixedClock) -> None:
    thread = services.create_thread(owner=owner, clock=clock)
    stale = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)
    clock.advance(services.STALE_RUN * 2)
    current = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)

    services.release_run(thread_id=thread.pk, token=stale, clock=clock)

    after = AssistantThread.objects.get(pk=thread.pk)
    assert (after.run_token, after.running_since) == (current, clock.now())


def test_title_is_collapsed_and_capped() -> None:
    assert services.thread_title("  What's\n\twaiting   on me? ") == "What's waiting on me?"
    title = services.thread_title("word " * 40)
    assert len(title) == services.TITLE_LENGTH
    assert title.endswith("…")


def test_dangling_tool_calls_get_a_stopped_result() -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    calls = [
        {"name": "get_item", "args": {}, "id": "c1"},
        {"name": "search_items", "args": {}, "id": "c2"},
        {"name": "send_email", "args": {}, "id": "c3"},
    ]
    messages = [
        HumanMessage("hi"),
        AIMessage(content="", tool_calls=calls),
        ToolMessage(content="{}", tool_call_id="c1", name="get_item"),
    ]

    stopped = runs.dangling_tool_results(messages, pending_tool_call_ids={"c3"})

    assert [(m.tool_call_id, m.name, m.status) for m in stopped] == [("c2", "search_items", "error")]
    assert (
        runs.dangling_tool_results([HumanMessage("hi"), AIMessage(content="Hello.")], pending_tool_call_ids=set()) == []
    )
    assert runs.dangling_tool_results([], pending_tool_call_ids=set()) == []


class _Memory:
    """A checkpointer factory over one InMemorySaver (a run and its follow-up read share it)."""

    def __init__(self, saver: InMemorySaver | None = None) -> None:
        self.saver = saver or InMemorySaver()

    def __call__(self) -> "_Memory":
        return self

    async def __aenter__(self) -> InMemorySaver:
        return self.saver

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.mark.django_db
def test_an_abandoned_claim_lapses_with_its_lease(owner: User, clock: FixedClock) -> None:
    thread = services.create_thread(owner=owner, clock=clock)
    services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)  # the response never started

    clock.advance(services.STALE_RUN / 2)
    with pytest.raises(Conflict):
        services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)

    clock.advance(services.STALE_RUN)
    services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)


@pytest.mark.django_db
def test_closing_a_body_that_never_started_releases_the_lease(owner: User, clock: FixedClock) -> None:
    thread = services.create_thread(owner=owner, clock=clock)
    token = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)
    frames = runs.stream_run(
        thread_id=thread.pk,
        viewer=owner,
        command=runs.StartRun(message_id="u1", content="hi"),
        token=token,
        model_factory=lambda: scripted("Hi."),
        checkpointer_factory=_Memory(),
        clock=clock,
    )
    body = runs.RunBody(frames, thread_id=thread.pk, token=token)
    response = StreamingHttpResponse(body)
    assert body.close in response._resource_closers  # pyrefly: ignore[missing-attribute]  # Django calls it from response.close()

    body.close()  # what response.close() does when the client left before the first byte

    services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)  # free right away, not after the lease


@pytest.mark.django_db
def test_the_heartbeat_keeps_a_long_runs_lease(owner: User, clock: FixedClock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runs, "HEARTBEAT_SECONDS", 0.05)
    thread = services.create_thread(owner=owner, clock=clock)
    token = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)

    async def run_past_the_lease() -> None:
        frames = runs.stream_run(
            thread_id=thread.pk,
            viewer=owner,
            command=runs.StartRun(message_id="u1", content="hi"),
            token=token,
            model_factory=lambda: SlowModel(messages=iter(["Done."]), delay=0.4),
            checkpointer_factory=_Memory(),
            clock=clock,
        )
        await anext(frames)
        clock.advance(services.STALE_RUN * 3)  # long past the lease taken at claim time
        await asyncio.sleep(0.2)  # the heartbeat renews meanwhile
        with pytest.raises(Conflict):
            await sync_to_async(services.claim_run)(thread_id=thread.pk, owner=owner, clock=clock)
        assert [f async for f in frames][-1].startswith(b"event: lifecycle")

    async_to_sync(run_past_the_lease)()

    assert AssistantThread.objects.get(pk=thread.pk).running_since is None


@pytest.mark.django_db
def test_a_lost_lease_stops_the_run(owner: User, clock: FixedClock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runs, "HEARTBEAT_SECONDS", 0.05)
    thread = services.create_thread(owner=owner, clock=clock)
    token = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)
    AssistantThread.objects.filter(pk=thread.pk).update(run_token=uuid.uuid4())  # another request took over

    async def run() -> list[bytes]:
        frames = runs.stream_run(
            thread_id=thread.pk,
            viewer=owner,
            command=runs.StartRun(message_id="u1", content="hi"),
            token=token,
            model_factory=lambda: SlowModel(messages=iter(["Never."]), delay=1),
            checkpointer_factory=_Memory(),
            clock=clock,
        )
        return [f async for f in frames]

    frames = async_to_sync(run)()

    assert runs.LEASE_LOST.encode() in frames[-1]
    assert AssistantThread.objects.get(pk=thread.pk).running_since is not None  # the new owner's lease stays


class _PruneFails(InMemorySaver):
    async def aprune(self, thread_ids: Sequence[str], *, strategy: str = "keep_latest") -> None:
        raise RuntimeError("deadlock detected")


@pytest.mark.django_db
def test_a_failed_prune_doesnt_fail_a_completed_run(
    owner: User, clock: FixedClock, caplog: pytest.LogCaptureFixture
) -> None:
    thread = services.create_thread(owner=owner, clock=clock)
    token = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)

    async def run() -> list[bytes]:
        frames = runs.stream_run(
            thread_id=thread.pk,
            viewer=owner,
            command=runs.StartRun(message_id="u1", content="hi"),
            token=token,
            model_factory=lambda: scripted("Hi."),
            checkpointer_factory=_Memory(_PruneFails()),
            clock=clock,
        )
        return [f async for f in frames]

    with caplog.at_level(logging.ERROR, logger="assistant.runs"):
        frames = async_to_sync(run)()

    terminal = [f for f in frames if f.startswith(b"event: lifecycle")][-1]
    assert b'"completed"' in terminal
    assert "assistant checkpoint prune failed" in caplog.text


@pytest.mark.django_db
def test_model_calls_and_the_run_total_are_logged(
    owner: User, clock: FixedClock, caplog: pytest.LogCaptureFixture
) -> None:
    from langchain_core.messages import AIMessage

    usage = {"input_tokens": 120, "output_tokens": 8, "total_tokens": 128, "input_token_details": {"cache_read": 100}}
    model = scripted(
        AIMessage(content="", tool_calls=[{"name": "get_queue_stats", "args": {}, "id": "c1"}], usage_metadata=usage),
        AIMessage(content="Two waiting.", usage_metadata=usage),
    )
    thread = services.create_thread(owner=owner, clock=clock)
    token = services.claim_run(thread_id=thread.pk, owner=owner, clock=clock)

    async def run() -> None:
        frames = runs.stream_run(
            thread_id=thread.pk,
            viewer=owner,
            command=runs.StartRun(message_id="u1", content="How many?"),
            token=token,
            model_factory=lambda: model,
            checkpointer_factory=_Memory(),
            clock=clock,
        )
        async for _ in frames:
            pass

    with caplog.at_level(logging.INFO):
        async_to_sync(run)()

    calls = [r for r in caplog.records if r.getMessage().startswith("assistant model call ")]
    assert len(calls) == 2
    # The numbers are in the text too: the console formatter drops `extra`.
    assert "cache_read_tokens=100" in calls[0].getMessage()
    assert "input_tokens=120" in calls[0].getMessage()
    first = calls[0].__dict__
    assert (first["thread_id"], first["model"]) == (str(thread.pk), "ToolCallingFakeModel")
    assert (first["input_tokens"], first["output_tokens"], first["cache_read_tokens"]) == (120, 8, 100)
    assert isinstance(first["latency_ms"], int)
    (record,) = [r for r in caplog.records if r.getMessage().startswith("assistant run ")]
    assert "outcome=completed" in record.getMessage()
    assert "cache_read_tokens=200" in record.getMessage()
    total = record.__dict__
    assert (total["outcome"], total["model_calls"], total["input_tokens"], total["cache_read_tokens"]) == (
        "completed",
        2,
        240,
        200,
    )
