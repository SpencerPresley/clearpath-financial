from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final
from unittest import mock

import pytest
from django.db import transaction

from accounts.models import User
from checks.tasks import run_llm_prereview
from demo.content import CATALOG
from demo.models import DemoReset
from demo.reset import SeedResult, _truncate, reset_demo
from imports.tasks import commit_import_task
from terms.tasks import fan_out_item_task

NOW: Final = datetime(2026, 10, 24, 22, 0, tzinfo=UTC)


@dataclass
class Seeded:
    result: SeedResult
    enqueued: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)  # Celery work started by the seed


def wipe() -> None:
    with transaction.atomic():
        _truncate()
        DemoReset.objects.all().delete()
        User.objects.filter(email__in=[p.email for p in CATALOG.personas]).delete()


@pytest.fixture(scope="module")
def seeded(django_db_setup: None, django_db_blocker: Any) -> Iterator[Seeded]:
    """Seed once per module and commit for real, so the on-commit hooks fire as they do in production (with
    every task the seed could start recorded instead of run), then wipe it all."""
    enqueued: list[tuple[str, tuple[Any, ...]]] = []

    def recorder(name: str) -> Any:
        return lambda *args, **_kwargs: enqueued.append((name, args))

    with (
        django_db_blocker.unblock(),
        mock.patch.object(run_llm_prereview, "delay", recorder("checks.run_llm_prereview")),
        mock.patch.object(fan_out_item_task, "delay", recorder("terms.fan_out_item")),
        mock.patch.object(commit_import_task, "delay", recorder("imports.commit")),
    ):
        result = reset_demo(now=NOW)
    yield Seeded(result=result, enqueued=enqueued)
    with django_db_blocker.unblock():
        wipe()
