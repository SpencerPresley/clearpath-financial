"""Fixtures shared by every app's tests."""

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from itertools import count

import pytest

from accounts.models import User
from core.clock import FixedClock
from core.domain import Role

TEST_PASSWORD = "correct-horse-battery"  # noqa: S105  # test-only credential

_emails = count(1)

type UserFactory = Callable[..., User]


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 24, 15, 0, tzinfo=UTC))


@pytest.fixture
def user_factory(db: None) -> UserFactory:  # noqa: ARG001  # requests DB access
    def make(
        *,
        roles: Iterable[Role] = (Role.MARKETER,),
        email: str | None = None,
        display_name: str | None = None,
        is_available: bool = True,
    ) -> User:
        n = next(_emails)
        return User.objects.create_user(
            email=email or f"user{n}@clearpath.test",
            password=TEST_PASSWORD,
            display_name=display_name or f"User {n}",
            roles=list(roles),
            is_available=is_available,
        )

    return make


@pytest.fixture
def marketer(user_factory: UserFactory) -> User:
    return user_factory(roles=[Role.MARKETER], display_name="Morgan Marketer")


@pytest.fixture
def reviewer(user_factory: UserFactory) -> User:
    return user_factory(roles=[Role.REVIEWER], display_name="Riley Reviewer")


@pytest.fixture
def lead(user_factory: UserFactory) -> User:
    return user_factory(roles=[Role.LEAD], display_name="Lee Lead")


@pytest.fixture
def admin_user(user_factory: UserFactory) -> User:
    return user_factory(roles=[Role.ADMIN], display_name="Avery Admin")
