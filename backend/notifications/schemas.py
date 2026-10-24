from datetime import datetime

from ninja import Schema
from pydantic import Field

from core.domain import NotificationKind, OutboxSource
from reviews.schemas import PartyRefOut


class NotificationOut(Schema):
    id: int
    kind: NotificationKind
    item_id: int | None
    item_key: str | None
    message: str
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
