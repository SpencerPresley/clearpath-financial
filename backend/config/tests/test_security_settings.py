"""Issue #18: admin login goes through allauth; the cache is Redis outside tests."""

import importlib
import os
from collections.abc import Callable, Iterator
from types import ModuleType

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


type Load = Callable[[str, str | None], ModuleType]


@pytest.fixture
def load_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Load]:
    """Import a settings module fresh under a given DJANGO_CSRF_TRUSTED_ORIGINS, then restore the originals.
    Django's own settings were read at startup, so reloading these modules doesn't change them."""

    def load(name: str, origins: str | None) -> ModuleType:
        monkeypatch.setenv("CLEARPATH_ENV_FILE", "")  # never the repo-root .env
        monkeypatch.setenv("POSTGRES_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "x"))
        if origins is None:
            monkeypatch.delenv("DJANGO_CSRF_TRUSTED_ORIGINS", raising=False)
        else:
            monkeypatch.setenv("DJANGO_CSRF_TRUSTED_ORIGINS", origins)
        importlib.reload(importlib.import_module("config.settings.base"))
        return importlib.reload(importlib.import_module(f"config.settings.{name}"))

    yield load
    monkeypatch.undo()
    for name in ("base", "dev", "prod"):
        importlib.reload(importlib.import_module(f"config.settings.{name}"))


def test_dev_trusts_local_vite_and_preview_ports_and_any_listed_origin(load_settings: Load) -> None:
    default = load_settings("dev", None).CSRF_TRUSTED_ORIGINS
    # An E2E run on another port lists it; the .env's usual single 5173 origin keeps the defaults too.
    extra = load_settings("dev", "http://localhost:4391,http://localhost:5173").CSRF_TRUSTED_ORIGINS

    assert {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"} <= set(default)
    assert set(extra) == {*default, "http://localhost:4391"}
    assert len(extra) == len(set(extra))


def test_prod_trusts_only_the_listed_origins(load_settings: Load) -> None:
    assert load_settings("prod", None).CSRF_TRUSTED_ORIGINS == []
    assert load_settings("prod", "https://review.clearpath.example").CSRF_TRUSTED_ORIGINS == [
        "https://review.clearpath.example"
    ]
