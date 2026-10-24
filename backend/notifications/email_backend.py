"""`EMAIL_BACKEND` for the demo: every email becomes an `OutboxEmail` row instead of mail.

- An approved assistant email carries `clearpath` metadata (who asked, who approved, which thread, which tool
  call), attached only by `assistant.email.send_approved_email` after the recipient allowlist and the human
  approval. It becomes an `assistant` row, shown to everyone.
- Anything else is the app's own mail, such as allauth's password reset (allauth renders it and sends it through
  `django.core.mail` and this backend like any Django email). It becomes a `system` row with every recipient,
  shown only to admins. Refusing it would turn the public reset endpoint into a 500.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend
from django.utils import timezone

from core.domain import OutboxSource
from notifications.models import OutboxEmail


@dataclass(frozen=True)
class OutboxMeta:
    requested_by_id: int
    approved_by_id: int
    thread_id: str
    tool_call_id: str
    item_id: int | None
    sent_at: datetime


def _html(message: EmailMessage) -> str:
    if isinstance(message, EmailMultiAlternatives):
        for content, mimetype in message.alternatives:
            if mimetype == "text/html":
                return str(content)
    return ""


class OutboxEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        sent = 0
        for message in email_messages:
            meta = getattr(message, "clearpath", None)
            if isinstance(meta, OutboxMeta):
                row = OutboxEmail.objects.create(
                    source=OutboxSource.ASSISTANT.value,
                    to=list(message.to),
                    subject=message.subject,
                    body=str(message.body),
                    html_body=_html(message),
                    item_id=meta.item_id,
                    requested_by_id=meta.requested_by_id,
                    approved_by_id=meta.approved_by_id,
                    thread_id=meta.thread_id,
                    tool_call_id=meta.tool_call_id,
                    sent_at=meta.sent_at,
                )
            else:
                row = OutboxEmail.objects.create(
                    source=OutboxSource.SYSTEM.value,
                    to=list(message.recipients()),
                    subject=message.subject,
                    body=str(message.body),
                    html_body=_html(message),
                    sent_at=timezone.now(),
                )
            message.outbox_id = row.pk  # pyrefly: ignore[missing-attribute]  # read back by the sender
            sent += 1
        return sent
