"""Running the agent inside a request and streaming it as SSE.

`stream_run` is the response body: a producer task drives the v3 stream into a queue of SSE frames; the
consumer (the response iterator) yields them, plus a keepalive comment whenever the producer has been quiet for
`KEEPALIVE_SECONDS`. If the client goes away, Django cancels the consumer: it aborts the run (state up to the
last finished step is already checkpointed), cancels the producer, and releases the lock. Every run ends with
one terminal `lifecycle` frame; a failure is one line, never an exception's text (which can carry a provider's
response body).

ORM calls go through `sync_to_async` (thread-sensitive), so they use the request's connection.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

import anthropic
from asgiref.sync import sync_to_async
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.stream.run_stream import AsyncGraphRunStream
from langgraph.types import Command
from pydantic import ValidationError

from accounts.models import User
from assistant import services
from assistant.agent import build_agent, state_graph
from assistant.checkpointer import open_checkpointer
from assistant.llm import AssistantNotConfigured, get_assistant_model
from assistant.schemas import AssistantThreadStateOut
from assistant.wire import KEEPALIVE, LifecycleEvent, lifecycle, sse_frame, thread_state, to_wire
from core.clock import SYSTEM_CLOCK, Clock
from reviews.selectors import ItemRow

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS: float = 15.0
REJECT_DEFAULT: Final = "The user declined to send this email. Don't send it again unless they ask."

type ModelFactory = Callable[[], BaseChatModel]
type CheckpointerFactory = Callable[[], AbstractAsyncContextManager[BaseCheckpointSaver]]

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
    decision: dict[str, Any]  # a HITL decision built by the API from the validated ApprovalResponseIn


type RunCommand = StartRun | Resume


@dataclass
class _Outcome:
    run: AsyncGraphRunStream | None = None
    awaiting_approval: bool | None = None


def _config(thread_id: UUID) -> RunnableConfig:
    return {"configurable": {"thread_id": str(thread_id)}}


def _input(command: RunCommand) -> dict[str, Any] | Command[Any]:
    if isinstance(command, StartRun):
        return {"messages": [HumanMessage(id=command.message_id, content=command.content)]}
    return Command(resume={command.interrupt_id: command.decision})


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


async def _produce(  # the run's inputs, all keyword-only
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
    try:
        model = model_factory()
        async with checkpointer_factory() as saver:
            item = command.item if isinstance(command, StartRun) else None
            agent = await sync_to_async(build_agent)(
                viewer=viewer, model=model, checkpointer=saver, item=item, clock=clock, thread_id=str(thread_id)
            )
            try:
                run = await agent.astream_events(_input(command), _config(thread_id), version="v3")
                outcome.run = run
                seen: set[str] = set()
                async for event in run:
                    for wire in to_wire(event, seen):
                        await queue.put(sse_frame(wire))
                terminal = "interrupted" if await run.interrupted() else "completed"
            except Exception as e:
                logger.exception("assistant run failed", extra={"thread_id": str(thread_id)})
                error = failure_message(e)
            outcome.awaiting_approval = await _pending(agent, thread_id)
            if terminal == "completed":
                # Keep only the latest checkpoint: the conversation lives in it; older steps are dead weight.
                await saver.aprune([str(thread_id)], strategy="keep_latest")
    except Exception as e:
        logger.exception("assistant run could not start", extra={"thread_id": str(thread_id)})
        terminal, error = "failed", failure_message(e)
    await queue.put(sse_frame(lifecycle(terminal, error)))
    await queue.put(None)


async def stream_run(  # the run's inputs, all keyword-only
    *,
    thread_id: UUID,
    viewer: User,
    command: RunCommand,
    claimed_at: datetime,
    model_factory: ModelFactory | None = None,
    checkpointer_factory: CheckpointerFactory | None = None,
    clock: Clock = SYSTEM_CLOCK,
) -> AsyncGenerator[bytes]:
    """SSE frames for one run on a thread whose lock the caller holds (`services.claim_run`); releases it."""
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
        if not producer.done():
            if outcome.run is not None:
                await outcome.run.abort()
            producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer
        await sync_to_async(services.release_run)(
            thread_id=thread_id,
            claimed_at=claimed_at,
            awaiting_approval=outcome.awaiting_approval,
            first_message=command.content if isinstance(command, StartRun) else None,
            clock=clock,
        )


async def pending_interrupt_ids(
    *, thread_id: UUID, viewer: User, checkpointer_factory: CheckpointerFactory | None = None
) -> set[str]:
    async with (checkpointer_factory or CHECKPOINTER_FACTORY)() as saver:
        snapshot = await state_graph(viewer=viewer, checkpointer=saver).aget_state(_config(thread_id))
    return {i.id for task in snapshot.tasks for i in task.interrupts}


async def read_state(
    *, thread_id: UUID, viewer: User, checkpointer_factory: CheckpointerFactory | None = None
) -> AssistantThreadStateOut:
    async with (checkpointer_factory or CHECKPOINTER_FACTORY)() as saver:
        snapshot = await state_graph(viewer=viewer, checkpointer=saver).aget_state(_config(thread_id))
    return thread_state(snapshot)
