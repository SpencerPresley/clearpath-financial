import pytest
from django.test import Client

from conftest import TEST_PASSWORD, UserFactory
from core.domain import Role

LOGIN_URL = "/_allauth/browser/v1/auth/login"


@pytest.mark.django_db
def test_headless_login_by_email_then_me(user_factory: UserFactory) -> None:
    user = user_factory(email="riley@clearpath.test", roles=[Role.REVIEWER], display_name="Riley")
    client = Client()

    login = client.post(
        LOGIN_URL,
        {"email": "Riley@ClearPath.test", "password": TEST_PASSWORD},
        content_type="application/json",
    )
    assert login.status_code == 200, login.content

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json() == {
        "id": user.pk,
        "email": "riley@clearpath.test",
        "display_name": "Riley",
        "roles": ["reviewer"],
        "effective_roles": ["reviewer"],
        "is_available": True,
    }


@pytest.mark.django_db
def test_headless_login_rejects_wrong_password(user_factory: UserFactory) -> None:
    user_factory(email="riley@clearpath.test")

    login = Client().post(
        LOGIN_URL, {"email": "riley@clearpath.test", "password": "nope-nope-nope"}, content_type="application/json"
    )

    assert login.status_code == 400


@pytest.mark.django_db
def test_me_requires_a_session() -> None:
    response = Client().get("/api/me")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
