"""The assistant agent: `create_agent` with the per-viewer tools and five middleware, outermost first.

1. `UsageLogMiddleware` logs every model call (model, tokens, latency) and adds it to the run's totals.
2. `RecipientAllowlistMiddleware` wraps `send_email` outside the approval gate:
   - a draft to an outside address (or an invalid draft) comes back to the model as an error `ToolMessage`
     and the user is never asked to approve it;
   - a call whose email the Outbox already has (its step was cut short after the send) returns the stored
     "sent" result, whatever the re-shown approval card is answered with;
   - a rejected call gets its "declined" outcome on the way back out.
   On resume, LangGraph re-runs every middleware listed before HITL up to the pause, so this one only reads.
   It sees the model's arguments; an edit made at approval is checked by the resume endpoint (422) and again
   by the tool.
3. `HumanInTheLoopMiddleware(per_call)`: one interrupt per `send_email` call, answered approve/edit/reject.
4. `ContextEditingMiddleware`: past 30k tokens, older tool results are replaced in the model request only.
5. `ModelCallLimitMiddleware`: at most 12 model calls per run, ending with product copy.
"""

import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from asgiref.sync import sync_to_async
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
)
from langchain.agents.middleware.types import (
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    hook_config,
)
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic import ValidationError

from accounts.models import User
from assistant.email import check_recipients, refused_recipients, sent_email
from assistant.prompt import system_message
from assistant.tools import (
    SEND_EMAIL,
    SendEmailArgs,
    build_tools,
    email_blocked_artifact,
    email_declined_artifact,
    sent_result,
)
from checks.llm.review import TokenUsage
from core.clock import SYSTEM_CLOCK, Clock
from core.errors import InvalidInput
from reviews.selectors import ItemRow

logger = logging.getLogger(__name__)

GRAPH_NAME: Final = "assistant"
MODEL_CALL_LIMIT: Final = 12
APPROVAL_DESCRIPTION: Final = "Review this email. Nothing is sent until you approve it."
CALL_LIMIT_REPLY: Final = f"I stopped after {MODEL_CALL_LIMIT} steps. Ask a narrower question or try again."
# Our reject message starts with this; HITL embeds the message verbatim in the ToolMessage it returns, so the
# "declined" outcome is recognized by our own words, not by the library's wording around them.
DECLINED_MARK: Final = "The user declined to send this email."

type ToolResult = ToolMessage | Command[Any]
type ModelResult = ModelResponse[Any] | AIMessage | ExtendedModelResponse[Any]


def reject_message(reason: str = "") -> str:
    """The message a rejected send returns to the model (and the marker of a "declined" outcome)."""
    reason = reason.strip()
    return (
        f"{DECLINED_MARK} Their reason: {reason}" if reason else f"{DECLINED_MARK} Don't send it again unless they ask."
    )


# --- usage logging (spec §6.4: model, tokens, latency, for cost tracking) ------------------------------------------


@dataclass
class RunUsage:
    """Totals for one run, filled in by `UsageLogMiddleware` and logged by the runner at the end."""

    model_calls: int = 0
    tokens: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: int = 0


def _ai_message(result: ModelResult) -> AIMessage | None:
    if isinstance(result, AIMessage):
        return result
    response = result.model_response if isinstance(result, ExtendedModelResponse) else result
    return next((m for m in response.result if isinstance(m, AIMessage)), None)


def kv(fields: Mapping[str, object]) -> str:
    """`key=value` pairs for a log line."""
    return " ".join(f"{key}={value}" for key, value in fields.items())


def _model_name(model: BaseChatModel) -> str:
    return str(getattr(model, "model", None) or getattr(model, "model_name", None) or type(model).__name__)


class UsageLogMiddleware(AgentMiddleware):
    def __init__(self, *, thread_id: str, usage: RunUsage) -> None:
        super().__init__()
        self.thread_id = thread_id
        self.usage = usage

    def _record(self, request: ModelRequest[Any], result: ModelResult, started: float) -> None:
        latency_ms = round((time.monotonic() - started) * 1000)
        message = _ai_message(result)
        tokens = TokenUsage.from_message(message) if message is not None else TokenUsage()
        self.usage.model_calls += 1
        self.usage.tokens += tokens
        self.usage.latency_ms += latency_ms
        fields = {
            "thread_id": self.thread_id,
            "model": _model_name(request.model),
            "input_tokens": tokens.input_tokens,
            "output_tokens": tokens.output_tokens,
            "cache_read_tokens": tokens.cache_read_tokens,
            "cache_creation_tokens": tokens.cache_creation_tokens,
            "latency_ms": latency_ms,
        }
        # In the text as well as `extra`: the plain console formatter drops `extra`, and these numbers are the
        # only evidence prompt caching engages (spec §6.4).
        logger.info("assistant model call %s", kv(fields), extra=fields)

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResult:
        started = time.monotonic()
        result = handler(request)
        self._record(request, result, started)
        return result

    async def awrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]]
    ) -> ModelResult:
        started = time.monotonic()
        result = await handler(request)
        self._record(request, result, started)
        return result


# --- send_email: allowlist, cut-short sends, declined outcome --------------------------------------------------------


def _refusal(tool_call: dict[str, Any], reason: str, *, refused: Sequence[str] = ()) -> ToolMessage:
    content = f"Not sent and not shown to the user. {reason}"
    return ToolMessage(
        content=content,
        name=SEND_EMAIL,
        tool_call_id=tool_call["id"],
        status="error",
        artifact=email_blocked_artifact(tool_call.get("args") or {}, refused=refused, reason=content),
    )


def _mark_declined(result: ToolResult, tool_call: dict[str, Any]) -> ToolResult:
    """HITL's reject answer comes back out through this middleware: record the outcome on it."""
    if isinstance(result, ToolMessage) and result.artifact is None and DECLINED_MARK in str(result.content):
        return result.model_copy(update={"artifact": email_declined_artifact(tool_call.get("args") or {})})
    return result


def recipient_refusal(tool_call: dict[str, Any]) -> ToolMessage | None:
    """The error the model gets instead of an approval prompt when a draft names an outside recipient (or
    isn't a valid draft at all, so every approval prompt carries a well-formed email)."""
    if tool_call.get("name") != SEND_EMAIL:
        return None
    try:
        draft = SendEmailArgs.model_validate(tool_call.get("args") or {})
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'arguments'}: {err['msg'].removeprefix('Value error, ')}"
            for err in e.errors()
        )
        return _refusal(tool_call, f"Invalid draft. {problems}".replace("\r", " ").replace("\n", " "))
    try:
        check_recipients(draft.to)
    except InvalidInput as e:
        reason = f"{e.message}. Only staff directory addresses receive email."
        return _refusal(tool_call, reason, refused=refused_recipients(draft.to))
    return None


def already_sent(tool_call: dict[str, Any], *, thread_id: str) -> ToolMessage | None:
    """The stored "sent" result when the Outbox already has this call's email. The step that sent it was cut
    short before its checkpoint, so the approval card came back; any answer to it resolves to what was sent."""
    if tool_call.get("name") != SEND_EMAIL or not thread_id or not tool_call.get("id"):
        return None
    sent = sent_email(thread_id=thread_id, tool_call_id=tool_call["id"])
    if sent is None:
        return None
    content, artifact = sent_result(sent)
    return ToolMessage(content=content, artifact=artifact, name=SEND_EMAIL, tool_call_id=tool_call["id"])


def _short_circuit(tool_call: dict[str, Any], thread_id: str) -> ToolMessage | None:
    return already_sent(tool_call, thread_id=thread_id) or recipient_refusal(tool_call)


class RecipientAllowlistMiddleware(AgentMiddleware):
    def __init__(self, *, thread_id: str = "") -> None:
        super().__init__()
        self.thread_id = thread_id

    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolResult]) -> ToolResult:
        call = dict(request.tool_call)
        early = _short_circuit(call, self.thread_id)
        return early if early is not None else _mark_declined(handler(request), call)

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolResult]]
    ) -> ToolResult:
        call = dict(request.tool_call)
        if call["name"] != SEND_EMAIL:
            return await handler(request)
        early = await sync_to_async(_short_circuit)(call, self.thread_id)
        return early if early is not None else _mark_declined(await handler(request), call)


class _ModelCallLimit(ModelCallLimitMiddleware):
    """The library's limit, ending the run with our copy instead of "Model call limits exceeded: …"."""

    @property
    def name(self) -> str:
        return "ModelCallLimitMiddleware"  # keeps the graph's node names (and existing checkpoints) unchanged

    @hook_config(can_jump_to=["end"])
    def before_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:  # noqa: ANN401
        result = super().before_model(state, runtime)
        if result and result.get("messages"):
            return {**result, "messages": [AIMessage(content=CALL_LIMIT_REPLY)]}
        return result


def middleware(*, thread_id: str = "", usage: RunUsage | None = None) -> Sequence[AgentMiddleware[Any, Any, Any]]:
    return [
        UsageLogMiddleware(thread_id=thread_id, usage=usage or RunUsage()),
        RecipientAllowlistMiddleware(thread_id=thread_id),
        HumanInTheLoopMiddleware(
            interrupt_on={
                SEND_EMAIL: {"allowed_decisions": ["approve", "edit", "reject"], "description": APPROVAL_DESCRIPTION}
            },
            interrupt_mode="per_call",
        ),
        ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=30_000, keep=4)]),
        _ModelCallLimit(run_limit=MODEL_CALL_LIMIT),
    ]


def _compile(
    model: BaseChatModel,
    tools: list[BaseTool],
    system: SystemMessage | None,
    checkpointer: BaseCheckpointSaver,
    stack: Sequence[AgentMiddleware[Any, Any, Any]],
) -> CompiledStateGraph:
    return create_agent(
        model,
        tools=tools,
        system_prompt=system,
        middleware=stack,
        checkpointer=checkpointer,
        name=GRAPH_NAME,
    )


def build_agent(  # the run's context, all keyword-only
    *,
    viewer: User,
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver,
    item: ItemRow | None = None,
    clock: Clock = SYSTEM_CLOCK,
    thread_id: str = "",
    usage: RunUsage | None = None,
) -> CompiledStateGraph:
    """Sync (the prompt reads the staff directory): call it through `sync_to_async` from async code."""
    tools = build_tools(viewer, clock=clock, thread_id=thread_id)
    system = system_message(viewer, item=item, clock=clock)
    return _compile(model, tools, system, checkpointer, middleware(thread_id=thread_id, usage=usage))


class _StateOnlyModel(BaseChatModel):
    """Stands in for the chat model in a graph used only to read checkpointed state, which never calls it."""

    @property
    def _llm_type(self) -> str:
        return "state-only"

    def _generate(
        self,
        messages: list[BaseMessage],  # noqa: ARG002
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: CallbackManagerForLLMRun | None = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ANN401, ARG002
    ) -> ChatResult:
        raise RuntimeError("A state-reading graph never calls the model.")


def state_graph(*, viewer: User, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    """The same graph shape as `build_agent` (nodes, tools, middleware), for `aget_state` without an API key.
    CPU only (no ORM): async callers run it in a worker thread (`sync_to_async(thread_sensitive=False)`) so a
    compile doesn't stall the event loop."""
    return _compile(_StateOnlyModel(), build_tools(viewer), None, checkpointer, middleware())
