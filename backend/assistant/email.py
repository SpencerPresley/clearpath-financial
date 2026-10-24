"""The assistant's one write: an internal email, sent only after a human approved the draft.

The recipient allowlist is code, not prompt (decisions.md "Assistant"): the assistant reads affiliate copy, so
injected text could ask it to mail data outside. Every recipient must be a bare address at exactly
`ASSISTANT_EMAIL_DOMAIN` that belongs to an active user or a team alias. It's checked three times: before the
approval interrupt (agent middleware), on an edited draft at the resume endpoint, and here at send time.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Final

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.template.loader import render_to_string

from accounts.models import User
from audit.payloads import EmailSentPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType
from core.errors import InvalidInput, NotFound
from notifications.email_backend import OutboxMeta
from reviews.models import ReviewItem

TO_FIELD: Final = "to"


@dataclass(frozen=True)
class EmailDraft:
    to: tuple[str, ...]
    subject: str
    body: str
    item_id: int | None


def at_internal_domain(address: str) -> bool:
    local, at, domain = address.rpartition("@")
    return bool(local) and at == "@" and "@" not in local and domain == settings.ASSISTANT_EMAIL_DOMAIN.lower()


def allowed_recipients() -> frozenset[str]:
    """Active users' emails and the team aliases, limited to the exact internal domain."""
    users = User.objects.filter(is_active=True).values_list("email", flat=True)
    candidates = {e.lower() for e in users} | {a.lower() for a in settings.ASSISTANT_TEAM_ADDRESSES}
    return frozenset(a for a in candidates if at_internal_domain(a))


def _bare_address(raw: str) -> str | None:
    """The address if `raw` is nothing but one address; `None` for display names, lists, or junk."""
    stripped = raw.strip()
    name, address = parseaddr(stripped)
    if name or not address or address != stripped:
        return None
    return address.lower()


def check_recipients(to: Sequence[str]) -> tuple[str, ...]:
    """Lower-cased, deduped recipients in order, or `InvalidInput` on `to` naming every address refused."""
    if not to:
        raise InvalidInput.for_field(TO_FIELD, "Add at least one recipient.")
    allowed = allowed_recipients()
    accepted: dict[str, None] = {}
    refused: list[str] = []
    for raw in to:
        address = _bare_address(raw)
        if address is None or address not in allowed:
            refused.append(raw.strip() or '""')
        else:
            accepted[address] = None
    if refused:
        raise InvalidInput.for_field(TO_FIELD, f"Not an internal address: {', '.join(refused)}")
    return tuple(accepted)


def _item(item_id: int | None) -> ReviewItem | None:
    if item_id is None:
        return None
    item = ReviewItem.objects.filter(pk=item_id).only("pk", "title").first()
    if item is None:
        raise NotFound.entity("item", item_id)
    return item


def send_approved_email(
    *, requester: User, approver: User, draft: EmailDraft, thread_id: str, clock: Clock = SYSTEM_CLOCK
) -> int:
    """Send an approved draft through `EMAIL_BACKEND` (the Outbox) and record `EMAIL_SENT`. Returns the
    OutboxEmail id."""
    with transaction.atomic():
        to = check_recipients(draft.to)
        item = _item(draft.item_id)
        now = clock.now()
        context = {
            "body": draft.body,
            "paragraphs": [p.strip() for p in draft.body.replace("\r\n", "\n").split("\n\n") if p.strip()],
            "item_key": item.key if item else None,
            "item_title": item.title if item else None,
            "item_url": f"{settings.FRONTEND_BASE_URL}/items/{item.pk}" if item else None,
            "requester": requester.display_name or requester.email,
            "approver": approver.display_name or approver.email,
        }
        message = EmailMultiAlternatives(
            subject=draft.subject,
            body=render_to_string("assistant/email.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=list(to),
            connection=get_connection(),
        )
        message.attach_alternative(render_to_string("assistant/email.html", context), "text/html")
        message.clearpath = OutboxMeta(  # pyrefly: ignore[missing-attribute]  # read by OutboxEmailBackend
            requested_by_id=requester.pk,
            approved_by_id=approver.pk,
            thread_id=thread_id,
            item_id=item.pk if item else None,
            sent_at=now,
        )
        message.send()
        outbox_id = getattr(message, "outbox_id", None)
        if not isinstance(outbox_id, int):
            raise RuntimeError("EMAIL_BACKEND didn't record the message in the Outbox")  # noqa: TRY004  # misconfiguration
        record_event(
            type=EventType.EMAIL_SENT,
            entity=EntityType.EMAIL,
            entity_id=outbox_id,
            payload=EmailSentPayload(email_id=outbox_id, to=to, subject=draft.subject, approved_by_id=approver.pk),
            actor=approver,
            at=now,
            item_id=item.pk if item else None,
        )
    return outbox_id
