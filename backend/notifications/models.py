from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from core.db import enum_choices
from core.domain import NotificationKind


class Notification(models.Model):
    """In-app only (spec §4.3 Notifications). Created by outbox handlers from events."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=enum_choices(NotificationKind))
    item = models.ForeignKey("reviews.ReviewItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    event = models.ForeignKey("audit.Event", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    message = models.CharField(max_length=500)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            # Belt and braces with the handler receipt: one notification per event per recipient.
            models.UniqueConstraint(
                fields=["event", "user"], condition=Q(event__isnull=False), name="notification_once_per_event"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="notification_user_idx"),
            models.Index(fields=["user"], condition=Q(read_at__isnull=True), name="notification_unread_idx"),
        ]

    def __str__(self) -> str:
        return self.message


class OutboxEmail(models.Model):
    """An email the assistant sent after a human approved it. The demo's stand-in for real mail; the
    recipient allowlist is enforced in the send tool's code (workstream K), not here."""

    to = ArrayField(models.EmailField())
    subject = models.CharField(max_length=300)
    body = models.TextField()
    item = models.ForeignKey("reviews.ReviewItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    thread_id = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(to__len__gte=1), name="outbox_email_has_recipient")]
        indexes = [models.Index(fields=["-sent_at"], name="outbox_email_sent_idx")]

    def __str__(self) -> str:
        return self.subject
