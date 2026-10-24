from datetime import datetime

from ninja import Schema

from core.domain import NotificationKind
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
    item_id: int | None
    requested_by: PartyRefOut
    approved_by: PartyRefOut
    thread_id: str
    sent_at: datetime
