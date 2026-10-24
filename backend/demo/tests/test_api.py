"""Reset demo through the API, and `seed_demo` on an empty database. Each test here runs a full seed."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client

from accounts.models import User
from demo import tasks
from demo.content.people import PERSONAS
from demo.users import demo_password, upsert_personas
from reviews.models import ReviewItem

pytestmark = pytest.mark.django_db

type OnCommit = Callable[..., AbstractContextManager[list[Callable[[], Any]]]]


def _signed_in(email: str) -> Client:
    client = Client()
    client.force_login(User.objects.get(email=email))
    return client


@pytest.fixture
def personas() -> dict[str, User]:
    return upsert_personas(PERSONAS, password=demo_password())


def test_seed_demo_on_an_empty_database_seeds_once() -> None:
    out = StringIO()
    call_command("seed_demo", stdout=out)
    counts = (ReviewItem.objects.filter(is_legacy=False).count(), ReviewItem.objects.filter(is_legacy=True).count())

    call_command("seed_demo", stdout=out)

    assert counts == (42, 178)
    assert (ReviewItem.objects.filter(is_legacy=False).count(), ReviewItem.objects.count()) == (42, 220)
    assert "nothing seeded" in out.getvalue()


def test_admin_resets_the_demo_and_stays_signed_in(
    personas: dict[str, User], django_capture_on_commit_callbacks: OnCommit
) -> None:
    client = _signed_in("admin@clearpath.demo")

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/api/admin/demo/reset")

    assert response.status_code == 202, response.content
    job = response.json()
    assert job["status"] == "queued"
    done = client.get(f"/api/admin/demo/resets/{job['id']}").json()
    assert (done["status"], done["seeded_items"], done["error"]) == ("done", 42, "")
    assert client.get("/api/me").status_code == 200
    assert ReviewItem.objects.filter(is_legacy=False).count() == 42


def test_a_second_request_while_one_is_queued_returns_it(
    personas: dict[str, User], django_capture_on_commit_callbacks: OnCommit
) -> None:
    client = _signed_in("admin@clearpath.demo")
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        first = client.post("/api/admin/demo/reset").json()
        second = client.post("/api/admin/demo/reset").json()

    assert first["id"] == second["id"]
    assert len(callbacks) == 1


@pytest.mark.parametrize("email", ["lead@clearpath.demo", "reviewer@clearpath.demo", "marketer@clearpath.demo"])
def test_only_admins_reset_or_read_resets(personas: dict[str, User], email: str) -> None:
    client = _signed_in(email)

    assert client.post("/api/admin/demo/reset").status_code == 403
    assert client.get("/api/admin/demo/resets/1").status_code == 403


def test_a_failed_reset_is_reported_on_the_job(
    personas: dict[str, User], monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks: OnCommit
) -> None:
    def broken(**_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "reset_demo", broken)
    client = _signed_in("admin@clearpath.demo")
    with django_capture_on_commit_callbacks(execute=True):
        job = client.post("/api/admin/demo/reset").json()

    failed = client.get(f"/api/admin/demo/resets/{job['id']}").json()
    assert failed["status"] == "failed"
    assert failed["error"] == tasks.FAILED_MESSAGE
