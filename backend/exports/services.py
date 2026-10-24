"""Export actions: request an xlsx of a view or an item's evidence pack, and the job that builds the file.

Builds run as Celery jobs (CloudFront drops origin requests idle for 60 s; ledger References). The request
enqueues the job on transaction commit, not through the outbox: "export requested" isn't a domain event. The
event that is, EXPORT_CREATED (data left the system), is recorded when the file is ready. Files are stored
through Django's storage API under a random name and served only by `downloadExport`.
"""

import logging
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from typing import IO, Final

from django.conf import settings
from django.core.files import File
from django.db import transaction

from accounts.models import User
from audit.payloads import ExportCreatedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import EntityType, EventType, Role
from core.errors import InvalidInput, NotFound
from core.permissions import require_role
from exports.domain import ExportKind, ExportStatus
from exports.evidence import can_read_partner_files, evidence_pack, latest_approval, write_evidence_pack
from exports.models import ExportJob
from exports.selectors import approved_item_ids, export_rows
from exports.xlsx import write_items_xlsx
from reviews.filters import ItemFilter, ItemSort
from reviews.models import ReviewItem

logger = logging.getLogger(__name__)

EXPORT_ROLES: Final = (Role.REVIEWER, Role.ADMIN)  # a lead is a reviewer (core.permissions.IMPLIED_ROLES)
ANY_ROLE: Final = tuple(Role)  # evidence packs: anyone who can read the item, which today is every role
MAX_EVIDENCE_PACKS: Final = 200
_SPOOL_BYTES: Final = 16 * 1024 * 1024
# A running job older than this lost its worker: the task can't outlive CELERY_TASK_TIME_LIMIT.
_STALE_AFTER: Final = timedelta(seconds=settings.CELERY_TASK_TIME_LIMIT + 60)


def _enqueue(job_id: int) -> None:
    from exports.tasks import run_export_task  # noqa: PLC0415  # tasks imports this module

    run_export_task.delay(job_id)


def request_export(
    *,
    actor: User,
    filters: ItemFilter,
    sort: ItemSort = ItemSort.NEWEST,
    include_evidence_packs: bool = False,
    clock: Clock = SYSTEM_CLOCK,
) -> int:
    """Queue an xlsx of the view (a zip with evidence packs if asked). Reviewers, leads, and admins."""
    require_role(actor, *EXPORT_ROLES)
    if include_evidence_packs:
        n = len(approved_item_ids(viewer=actor, filters=filters, sort=sort, clock=clock))
        if n > MAX_EVIDENCE_PACKS:
            raise InvalidInput.for_field(
                "include_evidence_packs",
                f"{n} items in this view have approvals; narrow it to {MAX_EVIDENCE_PACKS} or fewer for packs.",
            )
    with transaction.atomic():
        job = ExportJob.objects.create(
            kind=ExportKind.ITEMS_XLSX.value,
            filters=filters.model_dump(mode="json"),
            sort=sort.value,
            include_evidence_packs=include_evidence_packs,
            created_by=actor,
            created_at=clock.now(),
        )
        transaction.on_commit(lambda: _enqueue(job.pk))
    return job.pk


def request_evidence_pack(*, actor: User, item_id: int, clock: Clock = SYSTEM_CLOCK) -> int:
    """Queue an item's evidence pack zip. 409 if the item has no approval to record."""
    require_role(actor, *ANY_ROLE)
    item = ReviewItem.objects.filter(pk=item_id).first()
    if item is None:
        raise NotFound.entity("item", item_id)
    latest_approval(item)
    with transaction.atomic():
        job = ExportJob.objects.create(
            kind=ExportKind.EVIDENCE_PACK.value, item=item, created_by=actor, created_at=clock.now()
        )
        transaction.on_commit(lambda: _enqueue(job.pk))
    return job.pk


@dataclass(frozen=True)
class _Built:
    filename: str
    suffix: str
    item_count: int


def _build(job: ExportJob, out: IO[bytes], clock: Clock) -> _Built:
    today = clock.today().isoformat()
    if job.kind == ExportKind.EVIDENCE_PACK.value:
        pack = evidence_pack(item_id=job.item_id, clock=clock)  # pyrefly: ignore[missing-attribute, bad-argument-type]
        with zipfile.ZipFile(out, "w") as zf:
            write_evidence_pack(pack, zf, partner_files=can_read_partner_files(job.created_by))
        return _Built(f"{pack.item.key}-evidence-pack-{today}.zip", "zip", 1)

    viewer: User = job.created_by
    filters, sort = ItemFilter.model_validate(job.filters), ItemSort(job.sort)
    rows = export_rows(viewer=viewer, filters=filters, sort=sort, clock=clock)
    if not job.include_evidence_packs:
        return _Built(f"clearpath-items-{today}.xlsx", "xlsx", write_items_xlsx(rows, out))
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        with zf.open("items.xlsx", "w") as sheet:
            count = write_items_xlsx(rows, sheet)
        for item_id in approved_item_ids(viewer=viewer, filters=filters, sort=sort, clock=clock):
            pack = evidence_pack(item_id=item_id, clock=clock)
            write_evidence_pack(
                pack, zf, prefix=f"evidence-packs/{pack.item.key}/", partner_files=can_read_partner_files(viewer)
            )
    return _Built(f"clearpath-items-{today}.zip", "zip", count)


def run_export(*, job_id: int, clock: Clock = SYSTEM_CLOCK) -> None:
    """The export job. Claims the job in one short transaction, builds the file outside any transaction (a long
    one would hold back the outbox), and finishes in another. Runs a pending job, or a running one whose worker
    must have died (started longer ago than the task hard limit); anything else is left alone."""
    with transaction.atomic():
        job = ExportJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None:
            logger.info("export skipped job_id=%d: no such job", job_id)
            return
        started = job.started_at
        stale = job.status == ExportStatus.RUNNING.value and started is not None
        stale = stale and started is not None and started < clock.now() - _STALE_AFTER
        if not (job.status == ExportStatus.PENDING.value or stale):
            logger.info("export skipped job_id=%d status=%s", job_id, job.status)
            return
        job.status = ExportStatus.RUNNING.value
        job.started_at = clock.now()
        job.save(update_fields=["status", "started_at"])

    with tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES) as out:
        built = _build(job, out, clock)
        out.seek(0)
        now = clock.now()
        with transaction.atomic():
            job.file.save(f"{uuid.uuid4().hex}.{built.suffix}", File(out), save=False)
            job.filename = built.filename
            job.item_count = built.item_count
            job.status = ExportStatus.READY.value
            job.finished_at = now
            job.save(update_fields=["file", "filename", "item_count", "status", "finished_at"])
            record_event(
                type=EventType.EXPORT_CREATED,
                entity=EntityType.EXPORT,
                entity_id=job.pk,
                item_id=job.item_id,  # pyrefly: ignore[missing-attribute]
                payload=ExportCreatedPayload(export_id=job.pk, item_count=built.item_count),
                actor=job.created_by,
                at=now,
            )


def mark_export_failed(*, job_id: int, error: str, clock: Clock = SYSTEM_CLOCK) -> None:
    with transaction.atomic():
        job = ExportJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status == ExportStatus.READY.value:
            return
        job.status = ExportStatus.FAILED.value
        job.error = error[:500]
        job.finished_at = clock.now()
        job.save(update_fields=["status", "error", "finished_at"])
