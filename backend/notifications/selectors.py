from dataclasses import dataclass
from datetime import datetime

from accounts.models import User
from core.domain import NotificationKind
from core.errors import NotFound
from notifications.models import Notification, OutboxEmail
from reviews.selectors import PartyRef


@dataclass(frozen=True)
class NotificationRow:
    id: int
    kind: NotificationKind
    item_id: int | None
    item_key: str | None
    message: str
    read_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class NotificationPage:
    rows: tuple[NotificationRow, ...]
    unread_count: int


def list_notifications(*, user: User, unread_only: bool = False, limit: int = 50) -> NotificationPage:
    qs = Notification.objects.filter(user=user)
    unread = qs.filter(read_at__isnull=True)
    rows = (unread if unread_only else qs).order_by("-created_at", "-pk")[:limit]
    return NotificationPage(
        rows=tuple(
            NotificationRow(
                id=n.pk,
                kind=NotificationKind(n.kind),
                item_id=n.item_id,  # pyrefly: ignore[missing-attribute]
                item_key=f"CP-{n.item_id}" if n.item_id else None,  # pyrefly: ignore[missing-attribute]
                message=n.message,
                read_at=n.read_at,
                created_at=n.created_at,
            )
            for n in rows
        ),
        unread_count=unread.count(),
    )


@dataclass(frozen=True)
class OutboxEmailRow:
    id: int
    to: tuple[str, ...]
    subject: str
    body: str
    item_id: int | None
    requested_by: PartyRef
    approved_by: PartyRef
    thread_id: str
    sent_at: datetime


def _party(user: User) -> PartyRef:
    return PartyRef(id=user.pk, name=user.display_name or user.email)


def _email_row(e: OutboxEmail) -> OutboxEmailRow:
    return OutboxEmailRow(
        id=e.pk,
        to=tuple(e.to),
        subject=e.subject,
        body=e.body,
        item_id=e.item_id,  # pyrefly: ignore[missing-attribute]
        requested_by=_party(e.requested_by),
        approved_by=_party(e.approved_by),
        thread_id=e.thread_id,
        sent_at=e.sent_at,
    )


def list_outbox_emails(*, limit: int = 100) -> tuple[OutboxEmailRow, ...]:
    qs = OutboxEmail.objects.select_related("requested_by", "approved_by").order_by("-sent_at", "-pk")[:limit]
    return tuple(_email_row(e) for e in qs)


def get_outbox_email(*, email_id: int) -> OutboxEmailRow:
    email = OutboxEmail.objects.select_related("requested_by", "approved_by").filter(pk=email_id).first()
    if email is None:
        raise NotFound.entity("email", email_id)
    return _email_row(email)
