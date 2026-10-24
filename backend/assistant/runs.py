"""Running the agent inside a request and streaming it as SSE.

`stream_run` is the response body. Three tasks share one run:

- the **producer** drives the v3 stream into a queue of SSE frames and queues the terminal `lifecycle` frame as
  soon as the outcome is known (housekeeping like pruning comes after it and can't change it);
- the **heartbeat** renews the thread's run lease every `HEARTBEAT_SECONDS` for as long as the producer runs,
  however slowly the client reads; if the lease was lost (taken over after lapsing), it stops the run;
- the **consumer** (the response iterator) yields the frames, plus a keepalive comment whenever the producer
  has been quiet for `KEEPALIVE_SECONDS`.

If the client goes away, Django closes the consumer: it aborts the run (state up to the last finished step is
checkpointed), cancels the producer and heartbeat, and releases the lease. A body that is never iterated at all
releases through `RunBody.close()`; a claim whose response object never existed lapses with its lease. Every
run ends with one terminal `lifecycle` frame; a failure is one line, never an exception's text (which can carry
a provider's response body).

ORM calls go through `sync_to_async` (thread-sensitive), so they use the request's connection.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID

import anthropic
from asgiref.sync import sync_to_async
from langchain.agents.middleware.human_in_the_loop import ApproveDecision, EditDecision, RejectDecision
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.stream.run_stream import AsyncGraphRunStream
from langgraph.types import Command
from pydantic import ValidationError

from accounts.models import User
from assistant import services
from assistant.agent import RunUsage, build_agent, kv, reject_message, state_graph
from assistant.checkpointer import open_checkpointer
from assistant.llm import AssistantNotConfigured, get_assistant_model
from assistant.schemas import AssistantThreadStateOut
from assistant.selectors import RENEW_RUN
from assistant.wire import KEEPALIVE, LifecycleEvent, lifecycle, sse_frame, thread_state, to_wire
from core.clock import SYSTEM_CLOCK, Clock
from reviews.selectors import ItemRow

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS: float = 15.0
HEARTBEAT_SECONDS: float = RENEW_RUN.total_seconds()
REJECT_DEFAULT: Final = reject_message()
STOPPED_RESULT: Final = '{"error":"Stopped before it finished."}'
LEASE_LOST: Final = "This reply was stopped: the thread was busy for too long. Try again."

type ModelFactory = Callable[[], BaseChatModel]
type CheckpointerFactory = Callable[[], AbstractAsyncContextManager[BaseCheckpointSaver]]
type Decision = ApproveDecision | EditDecision | RejectDecision

# The API reads these at request time; tests swap in a scripted model (and may swap the checkpointer).
MODEL_FACTORY: ModelFactory = get_assistant_model
CHECKPOINTER_FACTORY: CheckpointerFactory = open_checkpointer


@dataclass(frozen=True)
class StartRun:
    message_id: str
    content: str
    item: ItemRow | None = None


@dataclass(frozen=True)
class Resume:
    interrupt_id: str
    decision: Decision  # built by the API from the validated ApprovalResponseIn


type RunCommand = StartRun | Resume


@dataclass
class _Outcome:
    run: AsyncGraphRunStream | None = None
    awaiting_approval: bool | None = None
    usage: RunUsage = field(default_factory=RunUsage)
    lease_lost: bool = False


def _config(thread_id: UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(thread_id)}}


def dangling_tool_results(messages: Sequence[BaseMessage], *, pending_tool_call_ids: set[str]) -> list[ToolMessage]:
    """Results for the last AI message's tool calls that never got one (a run cut short mid-tool), so the next
    request isn't a `tool_use` without its `tool_result` (Anthropic rejects that). Calls paused on an
    approval are left alone: that thread takes no new message until the approval is answered."""
    last_ai = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], AIMessage)), None)
    if last_ai is None:
        return []
    ai = messages[last_ai]
    assert isinstance(ai, AIMessage)  # noqa: S101  # narrowed by the search above
    answered = {m.tool_call_id for m in messages[last_ai + 1 :] if isinstance(m, ToolMessage)}
    return [
        ToolMessage(content=STOPPED_RESULT, tool_call_id=call["id"], name=call["name"], status="error")
        for call in ai.tool_calls
        if call["id"] and call["id"] not in answered and call["id"] not in pending_tool_call_ids
    ]


async def _input(agent: CompiledStateGraph, command: RunCommand, thread_id: UUID) -> dict[str, Any] | Command[Any]:
    if isinstance(command, Resume):
        return Command(resume={command.interrupt_id: command.decision})
    snapshot = await agent.aget_state(_config(thread_id))
    values = snapshot.values if isinstance(snapshot.values, dict) else {}
    paused = {
        str(i.value.get("tool_call_id"))
        for task in snapshot.tasks
        for i in task.interrupts
        if isinstance(i.value, dict)
    }
    stopped = dangling_tool_results(values.get("messages", []), pending_tool_call_ids=paused)
    return {"messages": [*stopped, HumanMessage(id=command.message_id, content=command.content)]}


def failure_message(error: BaseException) -> str:
    """One line for the user. The exception's own text stays in the log."""
    if isinstance(error, AssistantNotConfigured):
        return str(error)
    if isinstance(error, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return "The model provider refused the assistant's API key."
    if isinstance(error, anthropic.APIStatusError | anthropic.APIConnectionError):
        return "The model service is unavailable right now. Try again in a minute."
    if isinstance(error, ValidationError):
        return "That approval answer wasn't valid. Try again from the email card."
    return "Something went wrong running the assistant. Try again."


async def _pending(agent: CompiledStateGraph, thread_id: UUID) -> bool:
    snapshot = await agent.aget_state(_config(thread_id))
    return any(task.interrupts for task in snapshot.tasks)


def _log_run(thread_id: UUID, terminal: LifecycleEvent, usage: RunUsage) -> None:
    fields = {
        "thread_id": str(thread_id),
        "outcome": terminal,
        "model_calls": usage.model_calls,
        "input_tokens": usage.tokens.input_tokens,
        "output_tokens": usage.tokens.output_tokens,
        "cache_read_tokens": usage.tokens.cache_read_tokens,
        "cache_creation_tokens": usage.tokens.cache_creation_tokens,
        "latency_ms": usage.latency_ms,
    }
    logger.info("assistant run %s", kv(fields), extra=fields)


async def _produce(  # noqa: C901  # one decision per phase of the run, each with its own failure handling
    queue: asyncio.Queue[bytes | None],
    outcome: _Outcome,
    *,
    thread_id: UUID,
    viewer: User,
    command: RunCommand,
    model_factory: ModelFactory,
    checkpointer_factory: CheckpointerFactory,
    clock: Clock,
) -> None:
    await queue.put(sse_frame(lifecycle("running")))
    terminal: LifecycleEvent = "failed"
    error: str | None = None
    finished = False

    async def finish() -> None:
        nonlocal finished
        if not finished:
            finished = True
            _log_run(thread_id, terminal, outcome.usage)
            await queue.put(sse_frame(lifecycle(terminal, error)))

    try:
        model = model_factory()
        async with checkpointer_factory() as saver:
            item = command.item if isinstance(command, StartRun) else None
            agent = await sync_to_async(build_agent)(
                viewer=viewer,
                model=model,
                checkpointer=saver,
                item=item,
                clock=clock,
                thread_id=str(thread_id),
                usage=outcome.usage,
            )
            try:
                # durability="sync": a finished step is checkpointed before the next one starts, so a disconnect
                # later in the run can't lose it. A disconnect *during* the tools step still loses that step
                # (the sync send can't be cancelled, the step can): the approval comes back pending, and the
                # Outbox's per-tool-call record makes any answer to it report the email that was sent.
                run = await agent.astream_events(
                    await _input(agent, command, thread_id), _config(thread_id), version="v3", durability="sync"
                )
                outcome.run = run
                seen: set[str] = set()
                async for event in run:
                    for wire in to_wire(event, seen):
                        await queue.put(sse_frame(wire))
                terminal = "interrupted" if await run.interrupted() else "completed"
                if outcome.lease_lost:  # the heartbeat aborted the run: it didn't finish
                    terminal, error = "failed", LEASE_LOST
            except Exception as e:
                logger.exception("assistant run failed", extra={"thread_id": str(thread_id)})
                error = failure_message(e)
            await finish()  # the outcome is known: tell the client before any housekeeping
            try:
                outcome.awaiting_approval = await _pending(agent, thread_id)
            except Exception:
                logger.exception("assistant state read after the run failed", extra={"thread_id": str(thread_id)})
            if terminal == "completed":
                try:
                    # Keep only the latest checkpoint: the conversation lives in it. Housekeeping: the next
                    # completed run retries it, and it never changes this run's outcome.
                    await saver.aprune([str(thread_id)], strategy="keep_latest")
                except Exception:
                    logger.exception("assistant checkpoint prune failed", extra={"thread_id": str(thread_id)})
    except Exception as e:
        if not finished:
            logger.exception("assistant run could not start", extra={"thread_id": str(thread_id)})
            terminal, error = "failed", failure_message(e)
        else:
            logger.exception("assistant run cleanup failed", extra={"thread_id": str(thread_id)})
    await finish()
    await queue.put(None)


async def _heartbeat(
    queue: asyncio.Queue[bytes | None],
    outcome: _Outcome,
    producer: asyncio.Task[None],
    *,
    thread_id: UUID,
    token: UUID,
    clock: Clock,
) -> None:
    """Renew the lease while the producer runs. A lost lease means another request now owns the thread (ours
    lapsed): stop this run rather than have two agents write one checkpoint."""
    while not producer.done():
        await asyncio.sleep(HEARTBEAT_SECONDS)
        if producer.done():
            return
        if await sync_to_async(services.renew_run)(thread_id=thread_id, token=token, clock=clock):
            continue
        logger.warning("assistant run lease lost", extra={"thread_id": str(thread_id)})
        outcome.lease_lost = True
        if outcome.run is not None:
            await outcome.run.abort()  # the producer then reports the failure and ends the stream
            return
        producer.cancel()  # not streaming yet: stop it and end the stream here
        with suppress(asyncio.CancelledError):
            await producer
        await queue.put(sse_frame(lifecycle("failed", LEASE_LOST)))
        await queue.put(None)
        return


async def _stop(producer: asyncio.Task[None], heartbeat: asyncio.Task[None], outcome: _Outcome) -> None:
    heartbeat.cancel()
    if not producer.done():
        if outcome.run is not None:
            await outcome.run.abort()
        producer.cancel()
    for task in (producer, heartbeat):
        with suppress(asyncio.CancelledError):
            await task


async def stream_run(  # the run's inputs, all keyword-only
    *,
    thread_id: UUID,
    viewer: User,
    command: RunCommand,
    token: UUID,
    model_factory: ModelFactory | None = None,
    checkpointer_factory: CheckpointerFactory | None = None,
    clock: Clock = SYSTEM_CLOCK,
) -> AsyncGenerator[bytes]:
    """SSE frames for one run on a thread whose lease the caller holds (`services.claim_run`); releases it."""
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    outcome = _Outcome()
    producer = asyncio.create_task(
        _produce(
            queue,
            outcome,
            thread_id=thread_id,
            viewer=viewer,
            command=command,
            model_factory=model_factory or MODEL_FACTORY,
            checkpointer_factory=checkpointer_factory or CHECKPOINTER_FACTORY,
            clock=clock,
        )
    )
    heartbeat = asyncio.create_task(_heartbeat(queue, outcome, producer, thread_id=thread_id, token=token, clock=clock))
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
            except TimeoutError:
                yield KEEPALIVE
                continue
            if frame is None:
                break
            yield frame
    finally:
        cut_short = not producer.done()
        try:
            await _stop(producer, heartbeat, outcome)
            if cut_short and outcome.awaiting_approval is None:
                # Read what the checkpoint says now (an approval may have been answered and run).
                pending = await pending_interrupt_ids(
                    thread_id=thread_id, viewer=viewer, checkpointer_factory=checkpointer_factory
                )
                outcome.awaiting_approval = bool(pending)
        except Exception:
            logger.exception("assistant run shutdown failed", extra={"thread_id": str(thread_id)})
        finally:
            # Shielded: a second cancellation (server shutdown) mustn't skip giving the lease back.
            await asyncio.shield(
                sync_to_async(services.release_run)(
                    thread_id=thread_id,
                    token=token,
                    awaiting_approval=outcome.awaiting_approval,
                    first_message=command.content if isinstance(command, StartRun) else None,
                    clock=clock,
                )
            )


class RunBody:
    """The response body: `stream_run`'s frames, plus a sync `close()` (which Django's `StreamingHttpResponse`
    registers and calls via `response.close()`) that releases the lease when the body was never iterated. An
    async generator closed before its first `__anext__` never runs its `finally`, so without this a client that
    left before the first byte would hold the thread until the lease lapsed."""

    def __init__(self, frames: AsyncGenerator[bytes], *, thread_id: UUID, token: UUID) -> None:
        self._frames = frames
        self._thread_id = thread_id
        self._token = token
        self._started = False

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        self._started = True
        return await self._frames.__anext__()

    async def aclose(self) -> None:
        if self._started:
            await self._frames.aclose()
        else:
            await sync_to_async(self.close)()

    def close(self) -> None:
        if not self._started:
            self._started = True  # once
            services.release_run(thread_id=self._thread_id, token=self._token)


async def _state_graph(viewer: User, saver: BaseCheckpointSaver) -> CompiledStateGraph:
    return await sync_to_async(state_graph, thread_sensitive=False)(viewer=viewer, checkpointer=saver)


async def pending_interrupt_ids(
    *, thread_id: UUID, viewer: User, checkpointer_factory: CheckpointerFactory | None = None
) -> set[str]:
    async with (checkpointer_factory or CHECKPOINTER_FACTORY)() as saver:
        snapshot = await (await _state_graph(viewer, saver)).aget_state(_config(thread_id))
    return {i.id for task in snapshot.tasks for i in task.interrupts}


async def read_state(
    *, thread_id: UUID, viewer: User, run_alive: bool, checkpointer_factory: CheckpointerFactory | None = None
) -> AssistantThreadStateOut:
    async with (checkpointer_factory or CHECKPOINTER_FACTORY)() as saver:
        snapshot = await (await _state_graph(viewer, saver)).aget_state(_config(thread_id))
    return thread_state(snapshot, run_alive=run_alive)
