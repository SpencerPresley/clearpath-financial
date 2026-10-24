"""Reads for the drift monitor: each placement with a web address, its latest check, and its demo page if any."""

from dataclasses import dataclass
from datetime import datetime

from core.clock import SYSTEM_CLOCK, Clock
from core.domain import CheckStatus, DriftResult, DriftTrigger, Severity
from core.errors import NotFound
from drift import demo
from reviews.diff import DiffOp, DiffSegment
from reviews.models import Placement, ReviewItem, Snapshot
from reviews.selectors import PartyRef, live_placements_q


@dataclass(frozen=True)
class PageFinding:
    rule_id: str
    citation: str
    severity: Severity
    message: str
    suggested_fix: str | None
    quote: str | None
    new: bool  # the rule doesn't fire on the approved copy itself


@dataclass(frozen=True)
class SnapshotView:
    id: int
    placement_id: int
    status: CheckStatus
    trigger: DriftTrigger
    requested_by: PartyRef | None
    requested_at: datetime
    finished_at: datetime | None
    url: str
    final_url: str | None
    http_status: int | None
    title: str | None
    compared_version_n: int | None
    result: DriftResult | None
    score: float | None
    diff: tuple[DiffSegment, ...]
    findings: tuple[PageFinding, ...]
    error_code: str | None
    error_message: str | None
    reopened_item: bool


@dataclass(frozen=True)
class DemoPageRef:
    slug: str
    partner: str
    edited: bool
    edit_summary: str
    expected: str


@dataclass(frozen=True)
class PlacementDrift:
    placement_id: int
    location: str
    url: str
    monitored: bool
    is_live: bool
    latest: SnapshotView | None
    demo_page: DemoPageRef | None


@dataclass(frozen=True)
class ItemDrift:
    item_id: int
    placements: tuple[PlacementDrift, ...]


def snapshot_view(snapshot: Snapshot) -> SnapshotView:
    """Expects `requested_by` and `compared_version` selected (or None)."""
    by = snapshot.requested_by
    version = snapshot.compared_version
    return SnapshotView(
        id=snapshot.pk,
        placement_id=snapshot.placement_id,  # pyrefly: ignore[missing-attribute]
        status=CheckStatus(snapshot.status),
        trigger=DriftTrigger(snapshot.trigger),
        requested_by=PartyRef(id=by.pk, name=by.display_name or by.email) if by is not None else None,
        requested_at=snapshot.requested_at,
        finished_at=snapshot.finished_at,
        url=snapshot.url,
        final_url=snapshot.final_url or None,
        http_status=snapshot.http_status,
        title=snapshot.title or None,
        compared_version_n=version.n if version is not None else None,
        result=DriftResult(snapshot.result) if snapshot.result else None,
        score=snapshot.score,
        diff=tuple(DiffSegment(op=DiffOp(d["op"]), text=str(d["text"])) for d in snapshot.diff),
        findings=tuple(
            PageFinding(
                rule_id=str(f["rule_id"]),
                citation=str(f["citation"]),
                severity=Severity(f["severity"]),
                message=str(f["message"]),
                suggested_fix=f.get("suggested_fix"),
                quote=f.get("quote"),
                new=bool(f["new"]),
            )
            for f in snapshot.findings
        ),
        error_code=snapshot.error_code or None,
        error_message=snapshot.error_message or None,
        reopened_item=snapshot.reopen_event_id is not None,  # pyrefly: ignore[missing-attribute]
    )


def get_snapshot(*, snapshot_id: int) -> SnapshotView:
    snapshot = (
        Snapshot.objects.select_related("requested_by", "compared_version")
        .defer("text", "compared_version__content_text", "compared_version__search_vector")
        .filter(pk=snapshot_id)
        .first()
    )
    if snapshot is None:
        raise NotFound.entity("snapshot", snapshot_id)
    return snapshot_view(snapshot)


def _demo_ref(url: str) -> DemoPageRef | None:
    slug = demo.slug_for_url(url)
    page = demo.get_page(slug) if slug is not None else None
    if page is None:
        return None
    return DemoPageRef(
        slug=page.slug,
        partner=page.partner,
        edited=demo.is_edited(page.slug),
        edit_summary=page.edit_summary,
        expected=page.expected,
    )


def item_drift(*, item_id: int, clock: Clock = SYSTEM_CLOCK) -> ItemDrift:
    """Placements with a web address, in recorded order, each with its latest check. Three queries."""
    if not ReviewItem.objects.filter(pk=item_id).exists():
        raise NotFound.entity("item", item_id)
    placements = list(Placement.objects.filter(item_id=item_id).exclude(url="").order_by("first_run", "pk"))
    ids = [p.pk for p in placements]
    live = set(Placement.objects.filter(live_placements_q(clock.today()), pk__in=ids).values_list("pk", flat=True))
    latest = {
        s.placement_id: s  # pyrefly: ignore[missing-attribute]
        for s in Snapshot.objects.filter(placement_id__in=ids)
        .select_related("requested_by", "compared_version")
        .defer("text", "compared_version__content_text", "compared_version__search_vector")
        .order_by("placement_id", "-requested_at", "-pk")
        .distinct("placement_id")
    }
    return ItemDrift(
        item_id=item_id,
        placements=tuple(
            PlacementDrift(
                placement_id=p.pk,
                location=p.location,
                url=p.url,
                monitored=p.monitored,
                is_live=p.pk in live,
                latest=snapshot_view(latest[p.pk]) if p.pk in latest else None,
                demo_page=_demo_ref(p.url),
            )
            for p in placements
        ),
    )
