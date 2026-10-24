"""Read receipts on a user's own notifications. UI state, not domain state, so no event is recorded."""

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.errors import NotFound
from notifications.models import Notification


def mark_read(*, user: User, notification_id: int, clock: Clock = SYSTEM_CLOCK) -> None:
    mine = Notification.objects.filter(user=user, pk=notification_id)
    if not mine.exists():
        raise NotFound.entity("notification", notification_id)
    mine.filter(read_at__isnull=True).update(read_at=clock.now())


def mark_all_read(*, user: User, clock: Clock = SYSTEM_CLOCK) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=clock.now())
