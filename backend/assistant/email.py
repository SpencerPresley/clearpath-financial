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
from django.db.models.functions import Lower
from django.template.loader import render_to_string

from accounts.models import User
from audit.payloads import EmailSentPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType
from core.errors import InvalidInput, NotFound
from notifications.email_backend import OutboxMeta
from notifications.models import OutboxEmail
from reviews.models import ReviewItem

TO_FIELD: Final = "to"


@dataclass(frozen=True)
class SentEmail:
    """What the Outbox recorded: the truth about a send, whatever arguments a later replay carries."""

    outbox_id: int
    to: tuple[str, ...]
    item_id: int | None


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


def _allowed_among(addresses: set[str]) -> set[str]:
    """Which of these (bare, lower-cased) addresses may receive email: one query for just these candidates."""
    internal = {a for a in addresses if at_internal_domain(a)}
    aliases = {a.lower() for a in settings.ASSISTANT_TEAM_ADDRESSES} & internal
    users = (
        User.objects.annotate(lower_email=Lower("email"))
        .filter(is_active=True, lower_email__in=internal - aliases)
        .values_list("lower_email", flat=True)
    )
    return aliases | set(users)


def _sort_recipients(to: Sequence[str]) -> tuple[tuple[str, ...], list[str]]:
    """(accepted: lower-cased, deduped, in order; refused: the inputs as written, stripped)."""
    allowed = _allowed_among({a for a in (_bare_address(raw) for raw in to) if a is not None})
    accepted: dict[str, None] = {}
    refused: list[str] = []
    for raw in to:
        address = _bare_address(raw)
        if address is None or address not in allowed:
            refused.append(raw.strip() or '""')
        else:
            accepted[address] = None
    return tuple(accepted), refused


def refused_recipients(to: Sequence[str]) -> list[str]:
    return _sort_recipients(to)[1]


def check_recipients(to: Sequence[str]) -> tuple[str, ...]:
    """Lower-cased, deduped recipients in order, or `InvalidInput` on `to` naming every address refused."""
    if not to:
        raise InvalidInput.for_field(TO_FIELD, "Add at least one recipient.")
    accepted, refused = _sort_recipients(to)
    if refused:
        raise InvalidInput.for_field(TO_FIELD, f"Not an internal address: {', '.join(refused)}")
    return accepted


def _item(item_id: int | None) -> ReviewItem | None:
    if item_id is None:
        return None
    item = ReviewItem.objects.filter(pk=item_id).only("pk", "title").first()
    if item is None:
        raise NotFound.entity("item", item_id)
    return item


def send_approved_email(  # who, what, and where it came from
    *,
    requester: User,
    approver: User,
    draft: EmailDraft,
    thread_id: str,
    tool_call_id: str = "",
    clock: Clock = SYSTEM_CLOCK,
) -> SentEmail:
    """Send an approved draft through `EMAIL_BACKEND` (the Outbox) and record `EMAIL_SENT`.

    Idempotent per (thread, tool call): if a resumed run executes the same approved `send_email` again (the
    step that ran it was cut short before its checkpoint landed), the stored email comes back (its id and
    recipients, not this call's) and nothing is sent or recorded twice. The unique constraint backs this up."""
    with transaction.atomic():
        if tool_call_id and (sent := sent_email(thread_id=thread_id, tool_call_id=tool_call_id)) is not None:
            return sent
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
            tool_call_id=tool_call_id,
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
    return SentEmail(outbox_id=outbox_id, to=to, item_id=item.pk if item else None)


def sent_email(*, thread_id: str, tool_call_id: str) -> SentEmail | None:
    """The email an approved `send_email` call already produced, if any."""
    row = OutboxEmail.objects.filter(thread_id=thread_id, tool_call_id=tool_call_id).first()
    if row is None:
        return None
    return SentEmail(outbox_id=row.pk, to=tuple(row.to), item_id=row.item_id)  # pyrefly: ignore[missing-attribute]
