import uuid

import pytest
from django.test import Client

from accounts.models import User
from conftest import UserFactory


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_create_then_list_and_get_own_thread(reviewer: User) -> None:
    client = _client(reviewer)

    created = client.post("/api/assistant/threads")
    assert created.status_code == 201
    thread_id = created.json()["id"]

    assert [t["id"] for t in client.get("/api/assistant/threads").json()] == [thread_id]
    got = client.get(f"/api/assistant/threads/{thread_id}").json()
    assert got["title"] == ""
    assert got["awaiting_approval"] is False


@pytest.mark.django_db
def test_another_users_thread_is_not_found(reviewer: User, marketer: User) -> None:
    thread_id = _client(reviewer).post("/api/assistant/threads").json()["id"]

    other = _client(marketer)
    assert other.get(f"/api/assistant/threads/{thread_id}").status_code == 404
    assert other.get("/api/assistant/threads").json() == []


@pytest.mark.django_db
def test_unknown_thread_is_not_found(reviewer: User) -> None:
    assert _client(reviewer).get(f"/api/assistant/threads/{uuid.uuid4()}").status_code == 404


@pytest.mark.django_db
def test_user_without_roles_cannot_start_a_thread(user_factory: UserFactory) -> None:
    nobody = user_factory(roles=[])
    response = _client(nobody).post("/api/assistant/threads")
    assert response.status_code == 403
