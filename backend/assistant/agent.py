"""The assistant agent: `create_agent` with the per-viewer tools and four middleware, outermost first.

1. `RecipientAllowlistMiddleware` wraps `send_email` outside the approval gate, so a draft to an outside
   address comes back to the model as an error `ToolMessage` and the user is never asked to approve it.
   On resume, LangGraph re-runs every middleware listed before HITL up to the pause, so this one has no side
   effects. It sees the model's arguments only; an edit made at approval is checked by the resume endpoint
   (422) and again by the tool.
2. `HumanInTheLoopMiddleware(per_call)`: one interrupt per `send_email` call, answered approve/edit/reject.
3. `ContextEditingMiddleware`: past 30k tokens, older tool results are replaced in the model request only.
4. `ModelCallLimitMiddleware`: at most 12 model calls per run.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from asgiref.sync import sync_to_async
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
)
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import ValidationError

from accounts.models import User
from assistant.email import check_recipients
from assistant.prompt import system_message
from assistant.tools import SEND_EMAIL, SendEmailArgs, build_tools
from core.clock import SYSTEM_CLOCK, Clock
from core.errors import InvalidInput
from reviews.selectors import ItemRow

GRAPH_NAME = "assistant"
MODEL_CALL_LIMIT = 12
APPROVAL_DESCRIPTION = "Review this email. Nothing is sent until you approve it."

type ToolResult = ToolMessage | Command[Any]


def _refusal(tool_call: dict[str, Any], reason: str) -> ToolMessage:
    return ToolMessage(
        content=f"Not sent and not shown to the user. {reason}",
        name=SEND_EMAIL,
        tool_call_id=tool_call["id"],
        status="error",
    )


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
        return _refusal(tool_call, f"{e.message}. Only staff directory addresses receive email.")
    return None


class RecipientAllowlistMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], ToolResult]) -> ToolResult:
        refusal = recipient_refusal(dict(request.tool_call))
        return refusal if refusal is not None else handler(request)

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[ToolResult]]
    ) -> ToolResult:
        refusal = None
        if request.tool_call["name"] == SEND_EMAIL:
            refusal = await sync_to_async(recipient_refusal)(dict(request.tool_call))
        return refusal if refusal is not None else await handler(request)


def middleware() -> Sequence[AgentMiddleware[Any, Any, Any]]:
    return [
        RecipientAllowlistMiddleware(),
        HumanInTheLoopMiddleware(
            interrupt_on={
                SEND_EMAIL: {"allowed_decisions": ["approve", "edit", "reject"], "description": APPROVAL_DESCRIPTION}
            },
            interrupt_mode="per_call",
        ),
        ContextEditingMiddleware(edits=[ClearToolUsesEdit(trigger=30_000, keep=4)]),
        ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT),
    ]


def _compile(
    model: BaseChatModel, tools: list[BaseTool], system: SystemMessage | None, checkpointer: BaseCheckpointSaver
) -> CompiledStateGraph:
    return create_agent(
        model,
        tools=tools,
        system_prompt=system,
        middleware=middleware(),
        checkpointer=checkpointer,
        name=GRAPH_NAME,
    )


def build_agent(
    *,
    viewer: User,
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver,
    item: ItemRow | None = None,
    clock: Clock = SYSTEM_CLOCK,
    thread_id: str = "",
) -> CompiledStateGraph:
    """Sync (the prompt reads the staff directory): call it through `sync_to_async` from async code."""
    tools = build_tools(viewer, clock=clock, thread_id=thread_id)
    return _compile(model, tools, system_message(viewer, item=item, clock=clock), checkpointer)


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
    """The same graph shape as `build_agent` (nodes, tools, middleware), for `aget_state` without an API key."""
    return _compile(_StateOnlyModel(), build_tools(viewer), None, checkpointer)
