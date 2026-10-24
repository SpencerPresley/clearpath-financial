"""Reset demo through the API, and `seed_demo` on an empty database. Each test here runs a full seed."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import connection
from django.test import Client
from pytest_django import Settings

from accounts.models import User
from accounts.services import NewUser, UserChanges, create_user, update_user
from core.clock import FixedClock
from core.domain import Role
from demo import tasks
from demo.content.people import PERSONAS
from demo.reset import reset_demo
from demo.services import STALE_AFTER, STALE_MESSAGE, ResetStatus, get_reset, request_reset, start_reset
from demo.tests.conftest import NOW
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

    assert counts == (44, 178)
    assert (ReviewItem.objects.filter(is_legacy=False).count(), ReviewItem.objects.count()) == (44, 222)
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
    assert (done["status"], done["seeded_items"], done["error"]) == ("done", 44, "")
    assert client.get("/api/me").status_code == 200
    assert ReviewItem.objects.filter(is_legacy=False).count() == 44


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


def test_a_reset_refused_for_the_published_password_says_why(
    personas: dict[str, User],
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    django_capture_on_commit_callbacks: OnCommit,
) -> None:
    settings.DEMO_PASSWORD_DEFAULT_ALLOWED = False
    monkeypatch.setattr("demo.users.env.demo_user_password", None)
    client = _signed_in("admin@clearpath.demo")

    with django_capture_on_commit_callbacks(execute=True):
        job = client.post("/api/admin/demo/reset").json()

    failed = client.get(f"/api/admin/demo/resets/{job['id']}").json()
    assert failed["status"] == "failed"
    assert "DEMO_USER_PASSWORD isn't set" in failed["error"]
    assert not ReviewItem.objects.exists()


def test_a_reset_whose_worker_vanished_reads_as_failed_and_a_new_request_starts_fresh(
    personas: dict[str, User], django_capture_on_commit_callbacks: OnCommit
) -> None:
    """The message was lost (a worker crash after taking it): the row stays queued and nothing will run it."""
    admin = personas["admin"]
    asked = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    with django_capture_on_commit_callbacks(execute=False):
        lost = request_reset(actor=admin, clock=FixedClock(asked))
    later = FixedClock(asked + STALE_AFTER + timedelta(seconds=1))

    seen = get_reset(viewer=admin, reset_id=lost.id, clock=later)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        fresh = request_reset(actor=admin, clock=later)

    assert (seen.status, seen.error) == (ResetStatus.FAILED, STALE_MESSAGE)
    assert fresh.id != lost.id
    assert fresh.status == ResetStatus.QUEUED
    assert len(callbacks) == 1


def test_a_reset_within_the_window_is_still_in_flight(
    personas: dict[str, User], django_capture_on_commit_callbacks: OnCommit
) -> None:
    admin = personas["admin"]
    asked = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    with django_capture_on_commit_callbacks(execute=False):
        job = request_reset(actor=admin, clock=FixedClock(asked))

    seen = get_reset(viewer=admin, reset_id=job.id, clock=FixedClock(asked + STALE_AFTER - timedelta(seconds=1)))

    assert seen.status == ResetStatus.QUEUED


def test_a_reset_that_waited_in_the_queue_then_started_is_judged_by_its_start(
    personas: dict[str, User], django_capture_on_commit_callbacks: OnCommit
) -> None:
    """Queued 14 minutes behind other work, then picked up: at minute 16 it's mid-run, not dead."""
    admin = personas["admin"]
    asked = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)
    with django_capture_on_commit_callbacks(execute=False):
        job = request_reset(actor=admin, clock=FixedClock(asked))
    start_reset(reset_id=job.id, clock=FixedClock(asked + timedelta(minutes=14)))

    seen = get_reset(viewer=admin, reset_id=job.id, clock=FixedClock(asked + timedelta(minutes=16)))
    gone = get_reset(
        viewer=admin, reset_id=job.id, clock=FixedClock(asked + timedelta(minutes=14, seconds=1) + STALE_AFTER)
    )

    assert seen.status == ResetStatus.RUNNING
    assert gone.status == ResetStatus.FAILED


# --- Reset demo restores the seeded people ----------------------------------------------------------------------

STRONG = "plum-lantern-orbit-42"


def _people() -> dict[str, tuple[list[str], bool, bool]]:
    return {u.email: (u.roles, u.is_active, u.is_available) for u in User.objects.order_by("email")}


def _add(admin: User, email: str, roles: tuple[Role, ...]) -> User:
    new = NewUser(email=email, display_name=email.split("@", maxsplit=1)[0], roles=roles, password=STRONG)
    return User.objects.get(pk=create_user(actor=admin, new=new))


def _as_if_committed() -> None:
    """A real reset starts its own transaction. Here the test's one transaction still holds the deferred FK checks
    of the events written above, and TRUNCATE refuses to run past pending trigger events: fire them now."""
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_a_reset_restores_the_seeded_people_and_ends_added_users_sessions(personas: dict[str, User]) -> None:
    """Accounts added after the seed would lose their audit trail on reset (events are truncated), so they go too,
    and their sessions end. Seeded people get their seeded roles, active flag and availability back."""
    admin = personas["admin"]
    reset_demo(requested_by=admin, now=NOW)
    seeded = _people()
    jo = _add(admin, "jo@clearpath.demo", (Role.REVIEWER,))
    jo_client = _signed_in(jo.email)
    update_user(
        actor=admin, user_id=personas["sam"].pk, changes=UserChanges(roles=(Role.MARKETER,), is_available=False)
    )
    update_user(actor=admin, user_id=personas["nikhil"].pk, changes=UserChanges(is_active=False))
    update_user(actor=admin, user_id=personas["leah"].pk, changes=UserChanges(is_available=True))
    admin_client = _signed_in(admin.email)
    jo_session = jo_client.session.session_key
    _as_if_committed()

    reset_demo(requested_by=admin, now=NOW)

    assert _people() == seeded
    assert seeded["leah@clearpath.demo"] == (["reviewer"], True, False)  # out of office, as the story has it
    assert not User.objects.filter(email=jo.email).exists()
    assert not Session.objects.filter(session_key=jo_session).exists()
    assert jo_client.get("/api/me").status_code == 401
    assert admin_client.get("/api/me").status_code == 200


def test_an_added_admin_who_runs_the_reset_keeps_their_account(personas: dict[str, User]) -> None:
    ops = _add(personas["admin"], "ops@clearpath.demo", (Role.ADMIN,))
    temp = _add(personas["admin"], "temp@clearpath.demo", (Role.MARKETER,))
    client = _signed_in(ops.email)
    _as_if_committed()

    reset_demo(requested_by=ops, now=NOW)

    assert User.objects.filter(pk=ops.pk, is_active=True).exists()
    assert not User.objects.filter(pk=temp.pk).exists()
    assert client.get("/api/me").status_code == 200


def test_a_reset_keeps_operator_accounts(personas: dict[str, User]) -> None:
    """A django-admin superuser (manage.py createsuperuser) belongs to the deployment, not the demo."""
    operator = User.objects.create_superuser(email="ops-root@clearpath.test", password=STRONG)

    reset_demo(requested_by=personas["admin"], now=NOW)

    assert User.objects.filter(pk=operator.pk).exists()
