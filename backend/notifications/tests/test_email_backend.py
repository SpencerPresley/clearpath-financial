from collections.abc import Sequence

import pytest
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.db import IntegrityError
from django.test import Client
from pytest_django import Settings

from accounts.models import User
from core.clock import FixedClock
from core.domain import OutboxSource
from notifications.email_backend import OutboxEmailBackend
from notifications.models import SYSTEM_MAIL_BODY, OutboxEmail
from reviews.tests.factories import AT

OUTBOX_BACKEND = "notifications.email_backend.OutboxEmailBackend"


@pytest.mark.django_db
def test_mail_without_assistant_metadata_lands_as_system_mail(settings: Settings) -> None:
    settings.EMAIL_BACKEND = OUTBOX_BACKEND
    message = EmailMultiAlternatives(
        "Reset your password",
        "Use this link.",
        to=["dana@clearpath.demo"],
        cc=["ops@clearpath.demo"],
        connection=get_connection(OUTBOX_BACKEND, clock=FixedClock(AT)),
    )
    message.attach_alternative("<p>Use this link.</p>", "text/html")

    assert message.send() == 1

    row = OutboxEmail.objects.get()
    assert row.source == OutboxSource.SYSTEM
    assert row.to == ["dana@clearpath.demo", "ops@clearpath.demo"]
    # Metadata only: the body can hold a sign-in link, so it's never stored (an admin could take the account).
    assert (row.subject, row.body, row.html_body) == ("Reset your password", SYSTEM_MAIL_BODY, "")
    assert row.requested_by_id is None  # pyrefly: ignore[missing-attribute]
    assert row.approved_by_id is None  # pyrefly: ignore[missing-attribute]
    assert row.thread_id == ""
    assert row.sent_at == AT


@pytest.mark.django_db
def test_allauth_password_reset_lands_in_the_outbox_without_its_link(
    settings: Settings, marketer: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public reset endpoint must not 500: allauth's mail goes through EMAIL_BACKEND like any Django mail.
    What's stored is who it went to and when, never the reset link."""
    settings.EMAIL_BACKEND = OUTBOX_BACKEND
    captured: list[EmailMessage] = []
    send = OutboxEmailBackend.send_messages

    def spy(self: OutboxEmailBackend, messages: Sequence[EmailMessage]) -> int:
        captured.extend(messages)
        return send(self, messages)

    monkeypatch.setattr(OutboxEmailBackend, "send_messages", spy)

    response = Client().post(
        "/_allauth/browser/v1/auth/password/request", {"email": marketer.email}, content_type="application/json"
    )

    assert response.status_code == 200, response.content
    (sent,) = captured
    assert "/account/password/reset/" in sent.body  # allauth really did put a reset link in the mail
    row = OutboxEmail.objects.get()
    assert row.source == OutboxSource.SYSTEM
    assert row.to == [marketer.email]
    stored = f"{row.subject} {row.body} {row.html_body}"
    assert "http" not in stored
    assert "/account/password/reset/" not in stored
    key = sent.body.split("/account/password/reset/", 1)[1].split()[0]
    assert key not in stored


@pytest.mark.django_db
def test_the_database_refuses_a_system_row_with_a_body() -> None:
    with pytest.raises(IntegrityError):
        OutboxEmail.objects.create(
            source=OutboxSource.SYSTEM,
            to=["dana@clearpath.demo"],
            subject="Reset",
            body="https://x/reset/k",
            sent_at=AT,
        )
