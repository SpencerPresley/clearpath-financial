import pytest
from pytest_django import Settings

from accounts.models import User
from conftest import UserFactory
from core.domain import Role


@pytest.fixture(autouse=True)
def outbox_email_backend(settings: Settings) -> None:
    # Django's test setup swaps EMAIL_BACKEND for locmem; the assistant's send path is the Outbox backend.
    settings.EMAIL_BACKEND = "notifications.email_backend.OutboxEmailBackend"


@pytest.fixture
def dana(user_factory: UserFactory) -> User:
    """An active colleague at the allowlisted domain (fixture users default to @clearpath.test)."""
    return user_factory(roles=[Role.REVIEWER], email="dana@clearpath.demo", display_name="Dana Diaz")


@pytest.fixture
def owner(user_factory: UserFactory) -> User:
    return user_factory(roles=[Role.REVIEWER], email="riley@clearpath.demo", display_name="Riley Reviewer")
