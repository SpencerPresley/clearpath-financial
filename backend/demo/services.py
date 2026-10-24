"""Reset demo as an admin action: record the request, run it as a Celery job, report how it went.

A reset can take longer than CloudFront's 60 s origin timeout (ledger: long requests run as jobs), so the request
returns at once with a job the UI polls. A second request while one is queued or running gets that one back instead
of starting another. The job is enqueued on commit (the import/export ruling), not through the outbox: the event log
is about to be wiped, and the job itself is idempotent.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from django.db import connection, transaction

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Role
from core.errors import NotFound
from core.permissions import require_role
from demo.models import DemoReset
from demo.reset import SeedResult

logger = logging.getLogger(__name__)

# A queued or running reset older than this lost its worker; a new request starts a fresh one.
STALE_AFTER: Final = timedelta(minutes=15)
REQUEST_LOCK_KEY: Final = 0x4445_4D52  # "DEMR"


class ResetStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


IN_FLIGHT: Final = (ResetStatus.QUEUED.value, ResetStatus.RUNNING.value)


@dataclass(frozen=True)
class DemoResetJob:
    id: int
    status: ResetStatus
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    seeded_items: int
    error: str


def _job(row: DemoReset) -> DemoResetJob:
    return DemoResetJob(
        id=row.pk,
        status=ResetStatus(row.status),
        requested_at=row.requested_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        seeded_items=row.seeded_items,
        error=row.error,
    )


def _enqueue_task(reset_id: int) -> None:
    from demo.tasks import run_demo_reset  # noqa: PLC0415  # tasks imports this module

    run_demo_reset.delay(reset_id)


# Seam: tests replace it to observe or suppress the enqueue.
enqueue: Callable[[int], None] = _enqueue_task


def request_reset(*, actor: User, clock: Clock = SYSTEM_CLOCK) -> DemoResetJob:
    """Admins only. Returns the new job, or the one already in flight."""
    require_role(actor, Role.ADMIN)
    now = clock.now()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [REQUEST_LOCK_KEY])
        in_flight = (
            DemoReset.objects.filter(status__in=IN_FLIGHT, requested_at__gte=now - STALE_AFTER).order_by("-pk").first()
        )
        if in_flight is not None:
            return _job(in_flight)
        row = DemoReset.objects.create(status=ResetStatus.QUEUED.value, requested_by=actor, requested_at=now)
        reset_id = row.pk
        transaction.on_commit(lambda: enqueue(reset_id))
    return _job(row)


def get_reset(*, viewer: User, reset_id: int) -> DemoResetJob:
    require_role(viewer, Role.ADMIN)
    row = DemoReset.objects.filter(pk=reset_id).first()
    if row is None:
        raise NotFound.entity("demo reset", reset_id)
    return _job(row)


@dataclass(frozen=True)
class StartedReset:
    requested_by: User | None


def start_reset(*, reset_id: int, clock: Clock = SYSTEM_CLOCK) -> StartedReset | None:
    """queued (or running again, after a redelivery) -> running. None if there's nothing to run: a duplicate
    delivery of a job that already finished."""
    with transaction.atomic():
        row = (
            DemoReset.objects.select_for_update(of=("self",)).select_related("requested_by").filter(pk=reset_id).first()
        )
        if row is None or row.status not in IN_FLIGHT:
            return None
        row.status, row.started_at = ResetStatus.RUNNING.value, clock.now()
        row.save(update_fields=["status", "started_at"])
        return StartedReset(requested_by=row.requested_by)


def finish_reset(*, reset_id: int, result: SeedResult, clock: Clock = SYSTEM_CLOCK) -> None:
    DemoReset.objects.filter(pk=reset_id).update(
        status=ResetStatus.DONE.value, finished_at=clock.now(), seeded_items=result.items, error=""
    )


def fail_reset(*, reset_id: int, error: str, clock: Clock = SYSTEM_CLOCK) -> None:
    DemoReset.objects.filter(pk=reset_id).update(status=ResetStatus.FAILED.value, finished_at=clock.now(), error=error)
