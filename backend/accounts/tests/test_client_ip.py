"""allauth's rate limits key on the viewer IP CloudFront reports in CloudFront-Viewer-Address (prod.py), not on
X-Forwarded-For (client-controlled) or the socket peer (a CloudFront edge)."""

import pytest
from allauth.account.adapter import get_adapter
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory
from pytest_django import Settings

from conftest import UserFactory

LOGIN_URL = "/_allauth/browser/v1/auth/login"
HEADER = "CloudFront-Viewer-Address"


@pytest.fixture
def behind_cloudfront(settings: Settings) -> None:
    settings.ALLAUTH_TRUSTED_CLIENT_IP_HEADER = HEADER  # as prod.py
    cache.clear()  # allauth's rate-limit counters


@pytest.mark.usefixtures("behind_cloudfront")
def test_client_ip_is_the_viewer_address_without_its_port() -> None:
    request = RequestFactory().get(
        "/",
        headers={HEADER: "203.0.113.7:46532", "X-Forwarded-For": "198.51.100.1"},
        REMOTE_ADDR="130.176.0.1",  # a CloudFront edge
    )

    assert get_adapter().get_client_ip(request) == "203.0.113.7"


@pytest.mark.usefixtures("behind_cloudfront")
def test_without_the_header_allauth_refuses_rather_than_trusting_the_socket() -> None:
    request = RequestFactory().get("/", headers={"X-Forwarded-For": "198.51.100.1"}, REMOTE_ADDR="10.20.10.5")

    with pytest.raises(PermissionDenied):
        get_adapter().get_client_ip(request)


@pytest.mark.django_db
@pytest.mark.usefixtures("behind_cloudfront")
def test_requests_without_the_header_still_reach_health_and_allauth_config() -> None:
    """The compose healthcheck and deploy.sh call the app directly, with no CloudFront headers."""
    client = Client()

    assert client.get("/api/health").status_code == 200
    assert client.get("/_allauth/browser/v1/config").status_code == 200


@pytest.mark.django_db
@pytest.mark.usefixtures("behind_cloudfront")
def test_failed_logins_are_limited_per_viewer_even_when_x_forwarded_for_rotates(user_factory: UserFactory) -> None:
    def attempt(n: int, viewer: str) -> str:
        # A different email each time, so only the per-IP half of login_failed ("10/m/ip,5/300s/key") applies.
        user = user_factory()
        response = Client().post(
            LOGIN_URL,
            {"email": user.email, "password": "wrong-password-wrong"},
            content_type="application/json",
            headers={HEADER: f"{viewer}:{40000 + n}", "X-Forwarded-For": f"198.51.100.{n}"},
        )
        assert response.status_code == 400, response.content
        (error,) = response.json()["errors"]
        return error["code"]

    codes = [attempt(n, "203.0.113.7") for n in range(11)]

    assert codes[:10] == ["email_password_mismatch"] * 10
    assert codes[10] == "too_many_login_attempts"
    assert attempt(11, "203.0.113.8") == "email_password_mismatch"  # another viewer isn't affected
