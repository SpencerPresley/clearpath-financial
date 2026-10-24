import pytest
from django.core.mail import EmailMultiAlternatives, get_connection
from pytest_django import Settings

from notifications.models import OutboxEmail


@pytest.mark.django_db
def test_backend_refuses_a_message_without_assistant_metadata(settings: Settings) -> None:
    settings.EMAIL_BACKEND = "notifications.email_backend.OutboxEmailBackend"
    message = EmailMultiAlternatives("Hi", "body", to=["dana@clearpath.demo"], connection=get_connection())

    with pytest.raises(ValueError, match="only sends approved assistant email"):
        message.send()

    assert not OutboxEmail.objects.exists()
