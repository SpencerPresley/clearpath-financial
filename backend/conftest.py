"""Fixtures shared by every app's tests."""

import importlib
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from itertools import count
from typing import Any

import boto3
import pytest
from moto import mock_aws
from pytest_django import Settings

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


S3_TEST_BUCKET = "clearpath-documents-test"


@pytest.fixture
def s3_bucket(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Production's file storage (prod.py STORAGES, same options) against moto's in-memory S3, as a private bucket.
    Overriding STORAGES resets `default_storage`, so every FileField reads and writes here. Yields the boto3 Bucket."""
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(var, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        bucket = boto3.resource("s3", region_name="us-east-1").create_bucket(Bucket=S3_TEST_BUCKET)
        prod_default = importlib.import_module("config.settings.prod").STORAGES["default"]
        settings.STORAGES = {
            **settings.STORAGES,
            "default": {**prod_default, "OPTIONS": {**prod_default["OPTIONS"], "bucket_name": S3_TEST_BUCKET}},
        }
        yield bucket
