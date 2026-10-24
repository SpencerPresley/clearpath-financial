import pytest
from django.core.mail import EmailMultiAlternatives, get_connection
from django.test import Client
from pytest_django import Settings

from accounts.models import User
from core.domain import OutboxSource
from notifications.models import OutboxEmail

OUTBOX_BACKEND = "notifications.email_backend.OutboxEmailBackend"


@pytest.mark.django_db
def test_mail_without_assistant_metadata_lands_as_system_mail(settings: Settings) -> None:
    settings.EMAIL_BACKEND = OUTBOX_BACKEND
    message = EmailMultiAlternatives(
        "Reset your password",
        "Use this link.",
        to=["dana@clearpath.demo"],
        cc=["ops@clearpath.demo"],
        connection=get_connection(),
    )
    message.attach_alternative("<p>Use this link.</p>", "text/html")

    assert message.send() == 1

    row = OutboxEmail.objects.get()
    assert row.source == OutboxSource.SYSTEM
    assert row.to == ["dana@clearpath.demo", "ops@clearpath.demo"]
    assert (row.subject, row.body, row.html_body) == ("Reset your password", "Use this link.", "<p>Use this link.</p>")
    assert row.requested_by_id is None  # pyrefly: ignore[missing-attribute]
    assert row.approved_by_id is None  # pyrefly: ignore[missing-attribute]
    assert row.thread_id == ""


@pytest.mark.django_db
def test_allauth_password_reset_lands_in_the_outbox(settings: Settings, marketer: User) -> None:
    """The public reset endpoint must not 500: allauth's mail goes through EMAIL_BACKEND like any Django mail."""
    settings.EMAIL_BACKEND = OUTBOX_BACKEND

    response = Client().post(
        "/_allauth/browser/v1/auth/password/request", {"email": marketer.email}, content_type="application/json"
    )

    assert response.status_code == 200, response.content
    row = OutboxEmail.objects.get()
    assert row.source == OutboxSource.SYSTEM
    assert row.to == [marketer.email]
