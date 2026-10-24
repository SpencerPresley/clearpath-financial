"""Issue #18: admin login goes through allauth; the cache is Redis outside tests."""

import importlib
import os

import pytest
from django.test import Client

from accounts.models import User
from conftest import TEST_PASSWORD


@pytest.mark.django_db
def test_admin_login_redirects_to_the_spa_instead_of_taking_a_password(admin_user: User) -> None:
    User.objects.filter(pk=admin_user.pk).update(is_staff=True, is_superuser=True)
    client = Client()

    shown = client.get("/django-admin/login/")
    posted = client.post("/django-admin/login/", {"username": admin_user.email, "password": TEST_PASSWORD})

    assert shown.status_code == 302
    assert shown["Location"].startswith("http://localhost:5173/login?next=")
    assert posted.status_code == 302  # the admin form never authenticates
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_signed_in_staff_reach_the_admin_and_others_are_refused(admin_user: User, reviewer: User) -> None:
    User.objects.filter(pk=admin_user.pk).update(is_staff=True, is_superuser=True)
    staff, other = Client(), Client()
    staff.force_login(User.objects.get(pk=admin_user.pk))
    other.force_login(reviewer)

    assert staff.get("/django-admin/").status_code == 200
    assert other.get("/django-admin/login/").status_code == 403


def test_base_settings_use_the_redis_cache() -> None:
    os.environ.setdefault("POSTGRES_PASSWORD", "x")
    base = importlib.import_module("config.settings.base")

    assert base.CACHES["default"]["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert base.CACHES["default"]["LOCATION"] == base.env.redis_url
