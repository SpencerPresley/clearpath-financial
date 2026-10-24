"""Assistant API contract (docs/plan/assistant.md "Contract").

Threads are plain JSON. A run streams Server-Sent Events whose `data:` lines are LangChain Agent Streaming
Protocol (v2) events: `lifecycle`, `messages`, `tools`, `values`, `input.requested`. The frontend's
`AssistantTransport` (an `@langchain/react` `AgentServerAdapter`) consumes them; the protocol types come from
`@langchain/protocol`, so the stream itself has no schema component here. `getAssistantThreadState` returns the
protocol's `getState` shape, which hydrates `useStream` (messages and any pending approval).
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from ninja import Schema
from pydantic import AfterValidator, Field, JsonValue


class AssistantThreadOut(Schema):
    id: UUID
    title: str = Field(description='First message of the thread, trimmed; "" until the first run.')
    created_at: datetime
    updated_at: datetime
    awaiting_approval: bool = Field(description="The last run paused on an email that needs your approval.")


def _one_line(value: str) -> str:
    # A CR or LF in a header is header injection; Django would refuse it at send time (BadHeaderError).
    if "\r" in value or "\n" in value:
        raise ValueError("Subject must be one line.")
    return value


SubjectLine = Annotated[str, AfterValidator(_one_line)]


# --- run input ----------------------------------------------------------------------------------------------------


class AssistantUserMessageIn(Schema):
    id: str = Field(min_length=1, max_length=100, description="Client-minted id; the checkpoint keeps it.")
    content: str = Field(min_length=1, max_length=8_000)


class AssistantRunIn(Schema):
    message: AssistantUserMessageIn
    item_id: int | None = Field(default=None, description="The item open in the review screen, as context.")


class EmailDraftIn(Schema):
    to: list[str] = Field(min_length=1, max_length=20)
    subject: SubjectLine = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)
    item_key: str | None = Field(default=None, max_length=20, description="CP-<id> the email is about, if any.")


class ApproveIn(Schema):
    type: Literal["approve"]


class EditedActionIn(Schema):
    name: Literal["send_email"]
    args: EmailDraftIn


class EditIn(Schema):
    type: Literal["edit"]
    edited_action: EditedActionIn


class RejectIn(Schema):
    type: Literal["reject"]
    message: str = Field(default="", max_length=2_000, description="Why, for the assistant. Optional.")


ApprovalResponseIn = Annotated[ApproveIn | EditIn | RejectIn, Field(discriminator="type")]


class AssistantHistoryIn(Schema):
    """The SDK's `threads.getHistory` body; only `limit` is read, other keys are ignored."""

    limit: int | None = Field(default=None, ge=1, le=100)


# --- thread state (protocol getState shape) -----------------------------------------------------------------------


class WireToolCallOut(Schema):
    id: str | None
    name: str
    args: dict[str, JsonValue]
    type: Literal["tool_call"] = "tool_call"


class WireMessageOut(Schema):
    """A LangChain message as `BaseMessage.model_dump()` gives it, minus provider metadata."""

    type: Literal["human", "ai", "tool", "system"]
    id: str | None
    content: str | list[dict[str, JsonValue]]
    name: str | None = None
    tool_calls: list[WireToolCallOut] = Field(default_factory=list, description="ai messages only.")
    tool_call_id: str | None = Field(default=None, description="tool messages only.")
    status: Literal["success", "error"] | None = Field(default=None, description="tool messages only.")
    artifact: JsonValue = Field(
        default=None,
        description=(
            'tool messages, set by app code: {"item_keys": [...]} for links. send_email adds what happened: '
            '{"outcome": "sent", "outbox_id", "to", "item_keys"} | {"outcome": "declined", "to", "item_keys"} '
            '(the user rejected it) | {"outcome": "blocked", "refused", "reason", "to", "item_keys"} (refused '
            "before approval: outside recipients, or an invalid draft with refused = [])."
        ),
    )


class AssistantStateValuesOut(Schema):
    messages: list[WireMessageOut]


class EmailDraftOut(Schema):
    to: list[str]
    subject: str
    body: str
    item_key: str | None = None


class ToolApprovalOut(Schema):
    """HumanInTheLoopMiddleware's per-call interrupt value."""

    type: Literal["tool_approval"]
    tool_call_id: str
    name: Literal["send_email"]
    args: EmailDraftOut
    description: str


class InterruptOut(Schema):
    id: str
    value: ToolApprovalOut


class PendingTaskOut(Schema):
    id: str
    name: str
    interrupts: list[InterruptOut]


class CheckpointRefOut(Schema):
    checkpoint_id: str | None


class StateMetadataOut(Schema):
    step: int | None


class AssistantThreadStateOut(Schema):
    values: AssistantStateValuesOut
    next: list[str] = Field(description="Non-empty while a run is paused (approval pending).")
    tasks: list[PendingTaskOut]
    checkpoint: CheckpointRefOut | None
    metadata: StateMetadataOut | None
    created_at: datetime | None
