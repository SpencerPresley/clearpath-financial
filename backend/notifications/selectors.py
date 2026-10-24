from dataclasses import dataclass
from datetime import datetime

from django.db.models import QuerySet

from accounts.models import User
from core.domain import NotificationKind, OutboxSource, Role
from core.errors import NotFound
from core.permissions import has_role
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
    html_body: str
    item_id: int | None
    source: OutboxSource
    requested_by: PartyRef | None
    approved_by: PartyRef | None
    thread_id: str
    sent_at: datetime


def _party(user: User | None) -> PartyRef | None:
    return None if user is None else PartyRef(id=user.pk, name=user.display_name or user.email)


def _email_row(e: OutboxEmail) -> OutboxEmailRow:
    return OutboxEmailRow(
        id=e.pk,
        to=tuple(e.to),
        subject=e.subject,
        body=e.body,
        html_body=e.html_body,
        item_id=e.item_id,  # pyrefly: ignore[missing-attribute]
        source=OutboxSource(e.source),
        requested_by=_party(e.requested_by),
        approved_by=_party(e.approved_by),
        thread_id=e.thread_id,
        sent_at=e.sent_at,
    )


def _visible(viewer: User) -> QuerySet[OutboxEmail]:
    """System mail (password resets) is for admins; everyone sees what the assistant sent."""
    qs = OutboxEmail.objects.select_related("requested_by", "approved_by")
    return qs if has_role(viewer, Role.ADMIN) else qs.filter(source=OutboxSource.ASSISTANT.value)


def list_outbox_emails(*, viewer: User, limit: int = 100) -> tuple[OutboxEmailRow, ...]:
    return tuple(_email_row(e) for e in _visible(viewer).order_by("-sent_at", "-pk")[:limit])


def get_outbox_email(*, viewer: User, email_id: int) -> OutboxEmailRow:
    email = _visible(viewer).filter(pk=email_id).first()
    if email is None:
        raise NotFound.entity("email", email_id)
    return _email_row(email)
