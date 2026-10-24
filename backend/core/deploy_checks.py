"""Production runtime configuration: what the app refuses to run without.

One list of problems, enforced in three places, none of them at settings import (CI runs collectstatic on the prod
settings with no secrets, and `config/__init__` imports the Celery app into every management command):

- `manage.py check --deploy`: a deploy-tagged system check. deploy.sh runs it before migrate, so a bad
  configuration stops the deploy while the previous containers still serve.
- ASGI startup (`config/asgi.py`): a uvicorn worker raises before serving.
- Celery startup (`config/celery.py`): worker and beat exit before consuming or scheduling.

All of it is gated on `settings.PRODUCTION_CONFIG_REQUIRED` (prod.py), so dev and CI keep running without a key.
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register
from django.core.exceptions import ImproperlyConfigured

# What Terraform writes into /clearpath/prod/ANTHROPIC_API_KEY until the real key is put by hand
# (infra/main/config.tf, aws_ssm_parameter.anthropic_api_key.value_wo). render-env.sh sees the parameter as present.
ANTHROPIC_KEY_PLACEHOLDER = "placeholder-set-out-of-band"
# Anthropic API keys start with this; anything else is a paste of the wrong secret.
ANTHROPIC_KEY_PREFIX = "sk-ant-"


@dataclass(frozen=True)
class Problem:
    id: str
    msg: str
    hint: str


def _https_host(url: str) -> str | None:
    parts = urlsplit(url)
    return parts.hostname if parts.scheme == "https" and parts.hostname else None


def production_config_problems() -> list[Problem]:
    if not getattr(settings, "PRODUCTION_CONFIG_REQUIRED", False):
        return []
    problems: list[Problem] = []

    key: str | None = settings.ANTHROPIC_API_KEY
    if not key or key == ANTHROPIC_KEY_PLACEHOLDER or not key.startswith(ANTHROPIC_KEY_PREFIX):
        problems.append(
            Problem(
                "clearpath.E001",
                "ANTHROPIC_API_KEY is missing, still Terraform's placeholder, or not an Anthropic key. Without it every"
                " AI check fails as not_configured and every approval needs an override.",
                "aws ssm put-parameter --name /clearpath/prod/ANTHROPIC_API_KEY --type SecureString --overwrite"
                " (infra/README.md), then redeploy.",
            )
        )

    storage = settings.STORAGES["default"]
    if storage["BACKEND"] != "storages.backends.s3.S3Storage" or not storage.get("OPTIONS", {}).get("bucket_name"):
        problems.append(
            Problem(
                "clearpath.E002",
                "Uploaded files aren't stored in the documents bucket (DOCUMENTS_BUCKET unset or STORAGES not S3).",
                "Terraform writes /clearpath/prod/DOCUMENTS_BUCKET; check render-env.sh's output.",
            )
        )

    hosts: list[str] = list(settings.ALLOWED_HOSTS)
    if not hosts or "*" in hosts:
        problems.append(
            Problem(
                "clearpath.E003",
                f"ALLOWED_HOSTS must list the public host(s) explicitly, got {hosts!r}.",
                "Terraform writes /clearpath/prod/DJANGO_ALLOWED_HOSTS from the CloudFront domain.",
            )
        )

    frontend_host = _https_host(settings.FRONTEND_BASE_URL)
    if frontend_host is None or frontend_host not in hosts:
        problems.append(
            Problem(
                "clearpath.E004",
                f"FRONTEND_BASE_URL ({settings.FRONTEND_BASE_URL!r}) must be https:// on a host in ALLOWED_HOSTS:"
                " password-reset links, email item links and the admin's login redirect are built from it.",
                "Terraform writes /clearpath/prod/FRONTEND_BASE_URL as https://<CloudFront or custom domain>.",
            )
        )

    origins: list[str] = list(settings.CSRF_TRUSTED_ORIGINS)
    bad = [o for o in origins if _https_host(o) is None]
    if not origins or bad:
        problems.append(
            Problem(
                "clearpath.E005",
                f"CSRF_TRUSTED_ORIGINS must be https:// origins of the public site, got {origins!r}.",
                "Terraform writes /clearpath/prod/DJANGO_CSRF_TRUSTED_ORIGINS.",
            )
        )
    return problems


@register(Tags.security, deploy=True)
def check_production_config(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:  # noqa: ANN401, ARG001  # Django's check signature
    return [Error(p.msg, hint=p.hint, id=p.id) for p in production_config_problems()]


def require_production_config() -> None:
    """Raise if production is missing configuration it can't run without; a no-op outside production."""
    problems = production_config_problems()
    if problems:
        lines = "\n".join(f"  {p.id}: {p.msg}" for p in problems)
        raise ImproperlyConfigured(f"Refusing to start without production configuration:\n{lines}")
