"""Production refuses to run without its configuration (core/deploy_checks.py), but only where it runs: the
deploy check, ASGI and Celery startup. Importing the prod settings with no secrets (CI's collectstatic) still works."""

import importlib
import os
from collections.abc import Iterator

import pytest
from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from pytest_django import Settings

from config.celery import _require_production_config
from core.deploy_checks import (
    ANTHROPIC_KEY_PLACEHOLDER,
    production_config_problems,
    require_production_config,
)

HOST = "d111111abcdef8.cloudfront.net"


@pytest.fixture
def production(settings: Settings) -> Settings:
    """Test settings with production's requirements switched on and every one of them met."""
    settings.PRODUCTION_CONFIG_REQUIRED = True
    settings.ANTHROPIC_API_KEY = "sk-ant-api03-test"
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {"bucket_name": "documents"}},
    }
    settings.ALLOWED_HOSTS = [HOST, "localhost"]
    settings.CSRF_TRUSTED_ORIGINS = [f"https://{HOST}"]
    settings.FRONTEND_BASE_URL = f"https://{HOST}"
    return settings


def _ids() -> list[str]:
    return [p.id for p in production_config_problems()]


def test_nothing_is_required_outside_production(settings: Settings) -> None:
    settings.ANTHROPIC_API_KEY = None

    assert settings.PRODUCTION_CONFIG_REQUIRED is False
    assert production_config_problems() == []
    require_production_config()  # no-op


def test_a_complete_production_configuration_passes(production: Settings) -> None:
    assert production_config_problems() == []


@pytest.mark.parametrize("key", [None, "", ANTHROPIC_KEY_PLACEHOLDER, "sk-proj-not-anthropic"])
def test_production_needs_a_real_anthropic_key(production: Settings, key: str | None) -> None:
    production.ANTHROPIC_API_KEY = key

    assert _ids() == ["clearpath.E001"]


def test_production_needs_the_documents_bucket(production: Settings) -> None:
    production.STORAGES = {**production.STORAGES, "default": {**production.STORAGES["default"], "OPTIONS": {}}}
    assert _ids() == ["clearpath.E002"]

    production.STORAGES = {**production.STORAGES, "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}
    assert _ids() == ["clearpath.E002"]


@pytest.mark.parametrize(
    ("hosts", "frontend", "origins", "expected"),
    [
        ([], f"https://{HOST}", [f"https://{HOST}"], ["clearpath.E003", "clearpath.E004"]),
        (["*"], f"https://{HOST}", [f"https://{HOST}"], ["clearpath.E003", "clearpath.E004"]),
        ([HOST], f"http://{HOST}", [f"https://{HOST}"], ["clearpath.E004"]),
        ([HOST], "https://elsewhere.example", [f"https://{HOST}"], ["clearpath.E004"]),
        ([HOST], f"https://{HOST}", [], ["clearpath.E005"]),
        ([HOST], f"https://{HOST}", [f"http://{HOST}"], ["clearpath.E005"]),
    ],
)
def test_production_needs_https_urls_on_its_public_host(
    production: Settings, hosts: list[str], frontend: str, origins: list[str], expected: list[str]
) -> None:
    production.ALLOWED_HOSTS, production.FRONTEND_BASE_URL, production.CSRF_TRUSTED_ORIGINS = hosts, frontend, origins

    assert _ids() == expected


def test_the_check_is_registered_for_check_deploy_only(production: Settings) -> None:
    production.ANTHROPIC_API_KEY = None

    deploy = {m.id for m in run_checks(include_deployment_checks=True)}
    plain = {m.id for m in run_checks()}

    assert "clearpath.E001" in deploy
    assert "clearpath.E001" not in plain


def test_startup_guards_refuse_to_start(production: Settings) -> None:
    production.ANTHROPIC_API_KEY = ANTHROPIC_KEY_PLACEHOLDER

    with pytest.raises(ImproperlyConfigured, match=r"clearpath\.E001"):
        require_production_config()
    # Celery swallows Exceptions raised by signal receivers, so the worker/beat guard must exit instead.
    with pytest.raises(SystemExit) as exited:
        _require_production_config()
    assert exited.value.code == 1


def test_startup_guards_let_a_configured_production_start(production: Settings) -> None:
    require_production_config()
    _require_production_config()


@pytest.fixture
def prod_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Import config.settings.prod fresh with only what CI's collectstatic passes, then restore the originals."""
    monkeypatch.setenv("CLEARPATH_ENV_FILE", "")
    monkeypatch.setenv("POSTGRES_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "x"))
    for var in ("ANTHROPIC_API_KEY", "DOCUMENTS_BUCKET", "DJANGO_ALLOWED_HOSTS", "FRONTEND_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    yield
    monkeypatch.undo()
    for name in ("base", "prod"):
        importlib.reload(importlib.import_module(f"config.settings.{name}"))


@pytest.mark.usefixtures("prod_settings")
def test_prod_settings_import_without_secrets_and_use_s3_pool_and_the_cloudfront_ip_header() -> None:
    importlib.reload(importlib.import_module("config.settings.base"))
    prod = importlib.reload(importlib.import_module("config.settings.prod"))

    assert prod.PRODUCTION_CONFIG_REQUIRED is True
    assert prod.ANTHROPIC_API_KEY is None  # missing is refused at startup, not at import
    assert prod.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert prod.STORAGES["default"]["OPTIONS"]["file_overwrite"] is False
    assert "default_acl" not in prod.STORAGES["default"]["OPTIONS"]
    assert prod.STORAGES["staticfiles"]["BACKEND"] == "django.contrib.staticfiles.storage.StaticFilesStorage"
    assert prod.ALLAUTH_TRUSTED_CLIENT_IP_HEADER == "CloudFront-Viewer-Address"
    db = prod.DATABASES["default"]
    assert db["CONN_MAX_AGE"] == 0  # Django: required with the pool, and persistent connections are off under ASGI
    assert db["OPTIONS"]["pool"] == {"min_size": 1, "max_size": 8, "timeout": 10}
