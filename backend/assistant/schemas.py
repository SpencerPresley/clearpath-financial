"""Assistant contract (decisions.md "Assistant"). Replies stream over SSE: each `data:` line is one
`AssistantStreamEventOut` JSON object, ending with `done` or `error`. `send_email` always pauses with
`approval_required`; the human resolves it via `resolveAssistantApproval`, which streams the resumed run."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from ninja import Schema
from pydantic import Field, JsonValue


class AssistantRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class EmailDraftOut(Schema):
    to: list[str]
    subject: str
    body: str


class EmailDraftIn(Schema):
    to: list[str] = Field(min_length=1, max_length=20)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)


class PendingApprovalOut(Schema):
    interrupt_id: str
    tool: Literal["send_email"]
    draft: EmailDraftOut


class AssistantMessageOut(Schema):
    id: str
    role: AssistantRole
    content: str
    tool_name: str | None = None
    created_at: datetime


class AssistantThreadOut(Schema):
    id: str
    created_at: datetime
    messages: list[AssistantMessageOut]
    pending_approval: PendingApprovalOut | None


class AssistantMessageIn(Schema):
    content: str = Field(min_length=1, max_length=8_000)
    item_id: int | None = Field(default=None, description="The item open in the review screen, as context.")


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class AssistantApprovalIn(Schema):
    decision: ApprovalDecision
    edited: EmailDraftIn | None = Field(default=None, description="Required when decision is edit.")
    reason: str = Field(default="", max_length=2000)


# --- stream events ---------------------------------------------------------------------------------------------


class TokenEventOut(Schema):
    type: Literal["token"]
    text: str


class ToolCallEventOut(Schema):
    type: Literal["tool_call"]
    call_id: str
    name: str
    args: dict[str, JsonValue]


class ToolResultEventOut(Schema):
    type: Literal["tool_result"]
    call_id: str
    name: str
    summary: str = Field(description="One line for the panel, e.g. '12 items match'.")


class ApprovalRequiredEventOut(Schema):
    type: Literal["approval_required"]
    approval: PendingApprovalOut


class DoneEventOut(Schema):
    type: Literal["done"]
    message_id: str


class ErrorEventOut(Schema):
    type: Literal["error"]
    code: str
    message: str


AssistantStreamEventOut = Annotated[
    TokenEventOut | ToolCallEventOut | ToolResultEventOut | ApprovalRequiredEventOut | DoneEventOut | ErrorEventOut,
    Field(discriminator="type"),
]
