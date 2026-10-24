from django.http import HttpRequest
from ninja import Router, Status

from accounts.api import current_user
from core.schemas import ERRORS, PageLimit
from notifications import selectors, services
from notifications.schemas import MarkAllReadOut, NotificationPageOut, OutboxEmailOut

router = Router(tags=["notifications"])


@router.get("/notifications", response={200: NotificationPageOut, **ERRORS}, operation_id="listNotifications")
def list_notifications(
    request: HttpRequest, unread_only: bool = False, limit: PageLimit = 50
) -> selectors.NotificationPage:
    return selectors.list_notifications(user=current_user(request), unread_only=unread_only, limit=limit)


@router.post(
    "/notifications/{int:notification_id}/read", response={204: None, **ERRORS}, operation_id="markNotificationRead"
)
def mark_read(request: HttpRequest, notification_id: int) -> Status[None]:
    services.mark_read(user=current_user(request), notification_id=notification_id)
    return Status(204, None)


@router.post(
    "/notifications/read-all", response={200: MarkAllReadOut, **ERRORS}, operation_id="markAllNotificationsRead"
)
def mark_all_read(request: HttpRequest) -> MarkAllReadOut:
    return MarkAllReadOut(marked=services.mark_all_read(user=current_user(request)))


@router.get("/outbox", response={200: list[OutboxEmailOut], **ERRORS}, operation_id="listOutboxEmails")
def list_outbox(request: HttpRequest) -> list[selectors.OutboxEmailRow]:
    """Emails the assistant sent after a human approved them (the demo's stand-in for real mail)."""
    return list(selectors.list_outbox_emails())


@router.get("/outbox/{int:email_id}", response={200: OutboxEmailOut, **ERRORS}, operation_id="getOutboxEmail")
def get_outbox_email(request: HttpRequest, email_id: int) -> selectors.OutboxEmailRow:
    return selectors.get_outbox_email(email_id=email_id)
