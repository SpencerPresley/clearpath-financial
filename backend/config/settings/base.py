"""Base settings shared by dev, test, and prod.

Environment values are parsed once through `Env` so types are enforced at
startup: "false" is False, ports are ints, comma lists become lists, and every
missing required variable is reported together.
"""

import os
from pathlib import Path
from typing import Annotated, Any

from celery.schedules import crontab
from pydantic import BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# The repo-root .env is a 1Password-mounted named pipe locally. CI and test runs
# set CLEARPATH_ENV_FILE="" to skip it and rely on process environment only.
_env_file_setting = os.environ.get("CLEARPATH_ENV_FILE", str(REPO_ROOT / ".env"))
ENV_FILE: Path | None = Path(_env_file_setting) if _env_file_setting else None


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


# Comma-separated in the environment ("a.example,b.example"), a list in Python.
CsvList = Annotated[list[str], NoDecode, BeforeValidator(_split_csv)]


class Env(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    django_secret_key: SecretStr
    django_debug: bool = False
    django_allowed_hosts: CsvList = Field(default_factory=list)
    django_csrf_trusted_origins: CsvList = Field(default_factory=list)

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "clearpath"
    postgres_user: str = "clearpath"
    postgres_password: SecretStr

    redis_url: str = "redis://localhost:6379/0"

    frontend_base_url: str = "http://localhost:5173"

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-5-5"

    # Demo logins (seed_demo_users); optional so environments without demo users still boot.
    demo_user_password: SecretStr | None = None

    # Parallel worktrees share one Postgres; each gets its own test database.
    clearpath_test_db_suffix: str = ""


env = Env()  # pyrefly: ignore[missing-argument]  # populated from the environment

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = env.django_secret_key.get_secret_value()
DEBUG = env.django_debug
ALLOWED_HOSTS = env.django_allowed_hosts
CSRF_TRUSTED_ORIGINS = env.django_csrf_trusted_origins

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Before ninja: core overrides its export_openapi_schema command (core/management/commands).
    "core",
    "ninja",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.mfa",
    "accounts",
    "partners",
    "terms",
    "reviews",
    "checks",
    "audit",
    "notifications",
    "imports",
    "exports",
    "metrics",
    "assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES: dict[str, dict[str, Any]] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env.postgres_host,
        "PORT": env.postgres_port,
        "NAME": env.postgres_db,
        "USER": env.postgres_user,
        "PASSWORD": env.postgres_password.get_secret_value(),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- allauth (headless SPA + MFA) ---
# Accounts are provisioned by an admin, so there is no public signup.
HEADLESS_ONLY = True
HEADLESS_FRONTEND_URLS = {
    "account_reset_password_from_key": f"{env.frontend_base_url}/account/password/reset/{{key}}",
}
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_EMAIL_VERIFICATION = "none"

# Django admin signs in through the SPA (allauth headless: rate limits, MFA), not its own password form:
# config/urls.py wraps admin.site.login with allauth's secure_admin_login, which redirects here with ?next=.
# HEADLESS_ONLY removes allauth's server-rendered login page, so Django's default /accounts/login/ would 404.
LOGIN_URL = f"{env.frontend_base_url}/login"

# Shared across uvicorn workers and deploys, so allauth's rate-limit counters hold (issue #18). Django's
# built-in Redis backend; the client library comes with celery[redis]. Same Redis as the broker, keys prefixed.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env.redis_url,
        "KEY_PREFIX": "clearpath",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Evidence attachments. Local filesystem in dev; production overrides STORAGES with S3 (workstream A).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- LLM pre-review (checks.prereview) ---
# No key (dev, CI): every AI check ends `failed` with code not_configured, so Approve asks for an override reason.
ANTHROPIC_API_KEY: str | None = (
    env.anthropic_api_key.get_secret_value() if env.anthropic_api_key is not None else None
) or None
ANTHROPIC_MODEL = env.anthropic_model

# --- Celery ---
CELERY_BROKER_URL = env.redis_url
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULE = {
    # The event log is the outbox (decisions.md "Data"): poll it often; Redis is disposable.
    "dispatch-outbox": {"task": "audit.dispatch_outbox", "schedule": 2.0},
    "redeliver-stale-events": {"task": "audit.redeliver_stale_events", "schedule": 300.0},
    # Approval expiry and 30-day warnings (product-spec "Automation": daily sweep). 06:00 UTC = before the
    # US working day, so items land in the morning queue.
    "expiry-sweep": {"task": "reviews.expiry_sweep", "schedule": crontab(hour=6, minute=0)},
    # AI checks stuck `running` after a worker died flip to failed; pending ones whose message was lost re-enqueue.
    "reconcile-llm-checks": {"task": "checks.reconcile_llm_checks", "schedule": 120.0},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
