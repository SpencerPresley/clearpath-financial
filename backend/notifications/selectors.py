from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from django.db.models import QuerySet

from accounts.models import User
from audit.models import Event
from audit.payloads import (
    ApprovalExpiringPayload,
    CommentAddedPayload,
    DecisionRecordedPayload,
    EventPayload,
    ItemAssignedPayload,
    ItemReopenedPayload,
    PageFindingsFlaggedPayload,
    parse_payload,
)
from core.domain import AssignmentMode, DecisionOutcome, EventType, NotificationKind, OutboxSource, ReopenReason, Role
from core.errors import NotFound
from core.permissions import has_role
from notifications.models import Notification, OutboxEmail
from reviews.models import Version
from reviews.selectors import PartyRef

# What the source event says, per kind, so the inbox can phrase the row ("Dana Reyes requested changes on CP-42").
# Null on a row with no event or an event type the inbox doesn't phrase; the row's `message` covers those.


@dataclass(frozen=True)
class AssignmentDetail:
    mode: AssignmentMode
    kind: Literal["assignment"] = "assignment"


@dataclass(frozen=True)
class DecisionDetail:
    outcome: DecisionOutcome
    kind: Literal["decision"] = "decision"


@dataclass(frozen=True)
class RereviewDetail:
    reason: ReopenReason
    kind: Literal["rereview"] = "rereview"


@dataclass(frozen=True)
class MentionDetail:
    comment_id: int
    version_n: int  # the version the comment is on: the review screen shows comments per version
    kind: Literal["mention"] = "mention"


@dataclass(frozen=True)
class ExpiryWarningDetail:
    expires_at: datetime
    kind: Literal["expiry_warning"] = "expiry_warning"


@dataclass(frozen=True)
class PageFindingsDetail:
    new_blocking_count: int  # blocking rules on the partner page that don't fire on the approved copy
    kind: Literal["page_findings"] = "page_findings"


type NotificationDetail = (
    AssignmentDetail | DecisionDetail | RereviewDetail | MentionDetail | ExpiryWarningDetail | PageFindingsDetail
)


@dataclass(frozen=True)
class NotificationRow:
    id: int
    kind: NotificationKind
    item_id: int | None
    item_key: str | None
    item_title: str | None
    actor: PartyRef | None  # who caused it; None for system actions (sweeps, pool fan-out)
    detail: NotificationDetail | None
    message: str  # the stored one-liner, written when the notification was created
    read_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class NotificationPage:
    rows: tuple[NotificationRow, ...]
    unread_count: int


def _detail(payload: EventPayload | None, version_ns: dict[int, int]) -> NotificationDetail | None:
    detail: NotificationDetail | None = None
    match payload:
        case ItemAssignedPayload(mode=mode):
            detail = AssignmentDetail(mode=mode)
        case DecisionRecordedPayload(outcome=outcome):
            detail = DecisionDetail(outcome=outcome)
        case ItemReopenedPayload(reason=reason):
            detail = RereviewDetail(reason=reason)
        case CommentAddedPayload(comment_id=comment_id, version_id=version_id) if version_id in version_ns:
            detail = MentionDetail(comment_id=comment_id, version_n=version_ns[version_id])
        case ApprovalExpiringPayload(expires_at=expires_at):
            detail = ExpiryWarningDetail(expires_at=expires_at)
        case PageFindingsFlaggedPayload(rule_ids=rule_ids):
            detail = PageFindingsDetail(new_blocking_count=len(rule_ids))
    return detail


def _payload(event: Event | None) -> EventPayload | None:
    if event is None or event.type not in EventType:
        return None
    return parse_payload(EventType(event.type), event.payload)


def list_notifications(*, user: User, unread_only: bool = False, limit: int = 50) -> NotificationPage:
    """Newest first. Three queries whatever the page size: rows (with item, event and actor joined), the
    versions mentions point at, and the unread count."""
    qs = Notification.objects.filter(user=user)
    unread = qs.filter(read_at__isnull=True)
    notifications = list(
        (unread if unread_only else qs)
        .select_related("item", "event__actor")
        .only(
            *("id", "kind", "item_id", "message", "read_at", "created_at"),
            *("item__id", "item__title"),
            *("event__id", "event__type", "event__payload"),
            *("event__actor__id", "event__actor__display_name", "event__actor__email"),
        )
        .order_by("-created_at", "-pk")[:limit]
    )
    payloads = [_payload(n.event) for n in notifications]
    version_ids = {p.version_id for p in payloads if isinstance(p, CommentAddedPayload)}
    version_ns = dict(Version.objects.filter(pk__in=version_ids).values_list("pk", "n")) if version_ids else {}
    return NotificationPage(
        rows=tuple(
            NotificationRow(
                id=n.pk,
                kind=NotificationKind(n.kind),
                item_id=n.item_id,  # pyrefly: ignore[missing-attribute]
                item_key=n.item.key if n.item else None,
                item_title=n.item.title if n.item else None,
                actor=_party(n.event.actor if n.event else None),
                detail=_detail(payload, version_ns),
                message=n.message,
                read_at=n.read_at,
                created_at=n.created_at,
            )
            for n, payload in zip(notifications, payloads, strict=True)
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
