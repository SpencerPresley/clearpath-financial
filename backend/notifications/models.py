from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from core.domain import OutboxSource

# What a system row holds instead of its body. System mail (password resets, sign-in codes) carries live sign-in
# links; storing them would let anyone who can read the Outbox take over the account.
SYSTEM_MAIL_BODY = "Body not stored: system mail can contain sign-in links."


class Notification(models.Model):
    """In-app only (spec §4.3 Notifications). Created by outbox handlers from events."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20)
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
    """The demo's stand-in for real mail. Mostly emails the assistant sent after a person approved them (the
    recipient allowlist is enforced in the send tool's code, not here); also the app's own mail, such as
    allauth password resets (`source=system`: recipients, subject and time only, never the body; no requester,
    approver or thread; shown only to admins)."""

    source = models.CharField(max_length=20, default=OutboxSource.ASSISTANT.value)
    to = ArrayField(models.EmailField())
    subject = models.CharField(max_length=300)
    body = models.TextField()
    # The rendered HTML alternative (autoescaped template); "" for rows written before it existed.
    html_body = models.TextField(blank=True)
    item = models.ForeignKey("reviews.ReviewItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    thread_id = models.CharField(max_length=100, blank=True)
    # The approved send_email call that produced it: one email per (thread, tool call), however often it runs.
    tool_call_id = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(to__len__gte=1), name="outbox_email_has_recipient"),
            # An assistant email always records who asked and who approved. System mail has neither, and its body
            # is the placeholder: the database refuses a stored reset link.
            models.CheckConstraint(
                condition=(
                    Q(
                        source=OutboxSource.ASSISTANT.value,
                        requested_by__isnull=False,
                        approved_by__isnull=False,
                    )
                    | Q(
                        source=OutboxSource.SYSTEM.value,
                        requested_by__isnull=True,
                        approved_by__isnull=True,
                        thread_id="",
                        body=SYSTEM_MAIL_BODY,
                        html_body="",
                    )
                ),
                name="outbox_email_source_parties",
            ),
            models.UniqueConstraint(
                fields=["thread_id", "tool_call_id"],
                condition=~Q(tool_call_id=""),
                name="outbox_email_once_per_tool_call",
            ),
        ]
        indexes = [models.Index(fields=["-sent_at"], name="outbox_email_sent_idx")]

    def __str__(self) -> str:
        return self.subject
