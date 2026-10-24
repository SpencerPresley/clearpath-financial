"""`EMAIL_BACKEND` for the demo: an approved assistant email becomes an `OutboxEmail` row instead of mail.

Only `assistant.email.send_approved_email` attaches the `clearpath` metadata (who asked, who approved, which
thread), after the recipient allowlist and the human approval. A message without it is refused, so nothing
else (password resets, a stray `send_mail`) can write the Outbox by accident.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend

from notifications.models import OutboxEmail


@dataclass(frozen=True)
class OutboxMeta:
    requested_by_id: int
    approved_by_id: int
    thread_id: str
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
            if not isinstance(meta, OutboxMeta):
                raise ValueError(  # noqa: TRY004  # a refused message, not a programming-type error
                    "The Outbox backend only sends approved assistant email (no clearpath metadata)."
                )
            row = OutboxEmail.objects.create(
                to=list(message.to),
                subject=message.subject,
                body=str(message.body),
                html_body=_html(message),
                item_id=meta.item_id,
                requested_by_id=meta.requested_by_id,
                approved_by_id=meta.approved_by_id,
                thread_id=meta.thread_id,
                sent_at=meta.sent_at,
            )
            message.outbox_id = row.pk  # pyrefly: ignore[missing-attribute]  # read back by the sender
            sent += 1
        return sent
