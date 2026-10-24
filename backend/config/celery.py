import os
import sys
from typing import Any

from celery import Celery, signals
from django.core.exceptions import ImproperlyConfigured

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("clearpath")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@signals.worker_init.connect
@signals.beat_init.connect
def _require_production_config(**kwargs: Any) -> None:  # noqa: ANN401, ARG001  # signal kwargs
    """Worker and beat refuse to start without production configuration (core/deploy_checks.py). Not at module
    level: `config/__init__` imports this module into every management command, collectstatic in CI included.

    SystemExit, not the ImproperlyConfigured itself: Celery's Signal.send logs and swallows any Exception a receiver
    raises (celery/utils/dispatch/signal.py), so raising would only log and the worker would start anyway."""
    from core.deploy_checks import require_production_config  # noqa: PLC0415  # needs Django's app registry

    try:
        require_production_config()
    except ImproperlyConfigured as exc:
        print(exc, file=sys.stderr)  # noqa: T201  # the process is about to exit; logging may not be configured
        raise SystemExit(1) from exc
