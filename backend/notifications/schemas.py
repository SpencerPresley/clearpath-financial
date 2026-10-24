from datetime import datetime
from typing import Annotated, Literal

from ninja import Schema
from pydantic import Field

from core.domain import AssignmentMode, DecisionOutcome, NotificationKind, OutboxSource, ReopenReason
from reviews.schemas import PartyRefOut


class AssignmentDetailOut(Schema):
    kind: Literal["assignment"]
    mode: AssignmentMode


class DecisionDetailOut(Schema):
    kind: Literal["decision"]
    outcome: DecisionOutcome


class RereviewDetailOut(Schema):
    kind: Literal["rereview"]
    reason: ReopenReason


class MentionDetailOut(Schema):
    kind: Literal["mention"]
    comment_id: int
    version_n: int = Field(description="The version the comment is on (the review screen's `v`).")


class ExpiryWarningDetailOut(Schema):
    kind: Literal["expiry_warning"]
    expires_at: datetime


NotificationDetailOut = Annotated[
    AssignmentDetailOut | DecisionDetailOut | RereviewDetailOut | MentionDetailOut | ExpiryWarningDetailOut,
    Field(discriminator="kind"),
]


class NotificationOut(Schema):
    id: int
    kind: NotificationKind
    item_id: int | None
    item_key: str | None
    item_title: str | None
    actor: PartyRefOut | None = Field(description="Who caused it; null for system actions (sweeps, pool fan-out).")
    detail: NotificationDetailOut | None = Field(
        description="What the source event says, for phrasing the row; null when there's no event to read."
    )
    message: str = Field(description="The one-liner stored when it was created; the fallback when detail is null.")
    read_at: datetime | None
    created_at: datetime


class NotificationPageOut(Schema):
    rows: list[NotificationOut]
    unread_count: int


class MarkAllReadOut(Schema):
    marked: int


class OutboxEmailOut(Schema):
    id: int
    to: list[str]
    subject: str
    body: str
    html_body: str = Field(description="HTML alternative; render only in a sandboxed iframe.")
    item_id: int | None
    source: OutboxSource = Field(
        description="assistant: approved by a person. system: the app's own mail (admins only)."
    )
    requested_by: PartyRefOut | None = Field(description="null for system mail.")
    approved_by: PartyRefOut | None = Field(description="null for system mail.")
    thread_id: str
    sent_at: datetime
