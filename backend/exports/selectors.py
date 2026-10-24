"""Reads for exports: the rows of a filtered view, and export jobs (visible to their requester and to admins)."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Exists, F, OuterRef, QuerySet
from django.urls import reverse

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Channel, ItemStatus, Market, Product, RiskTier, Role
from core.errors import Conflict, NotFound
from core.permissions import has_role
from exports.domain import ExportKind, ExportStatus
from exports.models import ExportJob
from exports.xlsx import ExportRow
from reviews.filters import ItemFilter, ItemSort
from reviews.models import APPROVED_OUTCOMES, Decision, ReviewItem
from reviews.selectors import view_items


def _view(*, viewer: User, filters: ItemFilter, sort: ItemSort, clock: Clock) -> QuerySet[ReviewItem]:
    # The rows the queue list pages through, in its order (including the queue sort's implicit scope).
    return view_items(viewer=viewer, filters=filters, sort=sort, clock=clock)


def _name(user: User | None) -> str | None:
    return (user.display_name or user.email) if user is not None else None


def export_rows(
    *, viewer: User, filters: ItemFilter, sort: ItemSort, clock: Clock = SYSTEM_CLOCK
) -> Iterator[ExportRow]:
    """Rows of the view in its sort order, streamed in chunks. Legacy items show the tracker's people."""
    qs = (
        _view(viewer=viewer, filters=filters, sort=sort, clock=clock)
        .select_related("partner", "owner", "assignee")
        .annotate(current_version_n=F("current_version__n"))
    )
    for item in qs.iterator(chunk_size=1000):
        yield ExportRow(
            key=item.key,
            title=item.title,
            status=ItemStatus(item.status),
            product=Product(item.product),
            channel=Channel(item.channel),
            partner=item.partner.name if item.partner else None,
            risk_tier=RiskTier(item.risk_tier),
            round=item.round,
            version_n=getattr(item, "current_version_n", None),
            markets=tuple(Market(m) for m in item.markets),
            tags=tuple(item.tags),
            submitter=_name(item.owner) or item.legacy_submitter or None,
            reviewer=_name(item.assignee) or item.legacy_reviewer or None,
            open_findings=item.open_findings_count,
            submitted_on=item.submitted_at.date(),
            approved_on=item.approved_at.date() if item.approved_at else None,
            approval_expires_on=item.approval_expires_at.date() if item.approval_expires_at else None,
            legacy_ref=item.legacy_ref,
        )


def approved_item_ids(*, viewer: User, filters: ItemFilter, sort: ItemSort, clock: Clock = SYSTEM_CLOCK) -> list[int]:
    """Items in the view that have an approving decision: the ones an evidence pack can be built for."""
    approvals = Decision.objects.filter(item=OuterRef("pk"), outcome__in=APPROVED_OUTCOMES)
    qs = _view(viewer=viewer, filters=filters, sort=sort, clock=clock).filter(Exists(approvals))
    return list(qs.values_list("pk", flat=True))


@dataclass(frozen=True)
class ExportJobRow:
    id: int
    kind: ExportKind
    status: ExportStatus
    item_id: int | None
    item_count: int | None
    filename: str | None
    download_url: str | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


def _visible(viewer: User, export_id: int) -> ExportJob:
    job = ExportJob.objects.filter(pk=export_id).first()
    # Someone else's export is reported as missing, not forbidden: its existence isn't the viewer's business.
    if job is None or (job.created_by_id != viewer.pk and not has_role(viewer, Role.ADMIN)):  # pyrefly: ignore[missing-attribute]
        raise NotFound.entity("export", export_id)
    return job


def get_export(*, viewer: User, export_id: int) -> ExportJobRow:
    job = _visible(viewer, export_id)
    ready = job.status == ExportStatus.READY.value
    return ExportJobRow(
        id=job.pk,
        kind=ExportKind(job.kind),
        status=ExportStatus(job.status),
        item_id=job.item_id,  # pyrefly: ignore[missing-attribute]
        item_count=job.item_count,
        filename=job.filename or None,
        download_url=reverse("api:downloadExport", kwargs={"export_id": job.pk}) if ready else None,
        error=job.error or None,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def export_for_download(*, viewer: User, export_id: int) -> ExportJob:
    """For the download view only: the job, so the view can stream its file."""
    job = _visible(viewer, export_id)
    if job.status != ExportStatus.READY.value:
        raise Conflict(f"Export {job.pk} is {job.status}; download it once it's ready.")
    return job
