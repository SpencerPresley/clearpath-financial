import base64
import json
from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Count, Max, Q, Sum

from accounts.models import User
from checks.models import Finding
from core.domain import FindingSource, FindingState, ItemStatus, PartnerStatus, PartnerType, Severity
from core.errors import InvalidInput, NotFound, NotPermitted
from partners.models import Partner
from reviews.records import AttachmentRow, can_read_partner_attachments, list_partner_attachments


@dataclass(frozen=True)
class PartnerRow:
    id: int
    name: str
    type: PartnerType
    status: PartnerStatus
    item_count: int
    approved_count: int
    open_findings_count: int
    last_submitted_at: datetime | None


@dataclass(frozen=True)
class RepeatIssue:
    """A rule that keeps firing on this partner's content: the "repeat issues" panel."""

    rule_id: str
    citation: str
    count: int
    items: int
    last_seen_at: datetime


@dataclass(frozen=True)
class PartnerDetail(PartnerRow):
    website: str
    contact_email: str
    agreement_signed_on: date | None
    notes: str
    created_at: datetime
    attachments: tuple[AttachmentRow, ...]
    repeat_issues: tuple[RepeatIssue, ...]


def _with_counts():  # noqa: ANN202  # a Partner queryset with count annotations
    current = Q(items__is_legacy=False)
    return Partner.objects.annotate(
        item_count=Count("items", distinct=True),
        approved_count=Count("items", filter=Q(items__status=ItemStatus.APPROVED.value), distinct=True),
        open_findings_count=Sum("items__open_findings_count", filter=current, default=0),
        last_submitted_at=Max("items__submitted_at"),
    )


def _row(p: Partner) -> PartnerRow:
    return PartnerRow(
        id=p.pk,
        name=p.name,
        type=PartnerType(p.type),
        status=PartnerStatus(p.status),
        item_count=p.item_count,  # pyrefly: ignore[missing-attribute]
        approved_count=p.approved_count,  # pyrefly: ignore[missing-attribute]
        open_findings_count=p.open_findings_count,  # pyrefly: ignore[missing-attribute]
        last_submitted_at=p.last_submitted_at,  # pyrefly: ignore[missing-attribute]
    )


def list_partners(*, status: PartnerStatus | None = None, q: str | None = None) -> tuple[PartnerRow, ...]:
    qs = _with_counts().order_by("name")
    if status is not None:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(name__icontains=q)
    return tuple(_row(p) for p in qs)


def repeat_issues(*, partner_id: int, limit: int = 10) -> tuple[RepeatIssue, ...]:
    """Rules that fired more than once across the partner's items, excluding dismissed noise."""
    rows = (
        Finding.objects.filter(version__item__partner_id=partner_id)
        .exclude(state=FindingState.DISMISSED.value)
        .values("rule_id")
        .annotate(
            count=Count("pk"),
            items=Count("version__item", distinct=True),
            last_seen_at=Max("created_at"),
            citation=Max("citation"),
        )
        .filter(count__gt=1)
        .order_by("-count", "rule_id")[:limit]
    )
    return tuple(
        RepeatIssue(
            rule_id=r["rule_id"],
            citation=r["citation"],
            count=r["count"],
            items=r["items"],
            last_seen_at=r["last_seen_at"],
        )
        for r in rows
    )


def get_partner_detail(*, partner_id: int, viewer: User) -> PartnerDetail:
    """Attachments are empty for viewers who may not read them (marketers; ledger ruling)."""
    partner = _with_counts().filter(pk=partner_id).first()
    if partner is None:
        raise NotFound.entity("partner", partner_id)
    row = _row(partner)
    return PartnerDetail(
        **{field: getattr(row, field) for field in PartnerRow.__dataclass_fields__},
        website=partner.website,
        contact_email=partner.contact_email,
        agreement_signed_on=partner.agreement_signed_on,
        notes=partner.notes,
        created_at=partner.created_at,
        attachments=list_partner_attachments(partner_id=partner_id, viewer=viewer)
        if can_read_partner_attachments(viewer)
        else (),
        repeat_issues=repeat_issues(partner_id=partner_id),
    )


# --- findings history ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PartnerFindingRow:
    """One finding on one version of one of the partner's items: the partner's findings history."""

    id: int
    item_id: int
    item_key: str
    item_title: str
    item_is_legacy: bool
    version_n: int
    rule_id: str
    citation: str
    source: FindingSource
    severity: Severity
    state: FindingState
    message: str
    created_at: datetime


@dataclass(frozen=True)
class PartnerFindingPage:
    rows: tuple[PartnerFindingRow, ...]
    next_cursor: str | None


def _encode_finding_cursor(finding: Finding) -> str:
    raw = json.dumps({"at": finding.created_at.isoformat(), "id": finding.pk}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_finding_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        return datetime.fromisoformat(data["at"]), int(data["id"])
    except (ValueError, KeyError, TypeError) as exc:  # binascii.Error is a ValueError
        raise InvalidInput(
            "This page link is out of date. Reload the list.", fields=[], details={"field": "cursor"}
        ) from exc


def list_partner_findings(
    *, partner_id: int, viewer: User, cursor: str | None = None, limit: int = 50
) -> PartnerFindingPage:
    """Every finding on any version of the partner's items, newest first (ties by id), one page per call.

    Reviewers, leads, and admins (as for partner agreements: the history is a review tool). Two queries: the
    partner's existence and the page."""
    if not can_read_partner_attachments(viewer):
        raise NotPermitted("A partner's findings history is for reviewers and leads.")
    if not Partner.objects.filter(pk=partner_id).exists():
        raise NotFound.entity("partner", partner_id)
    qs = Finding.objects.filter(version__item__partner_id=partner_id)
    if cursor is not None:
        at, pk = _decode_finding_cursor(cursor)
        qs = qs.filter(Q(created_at__lt=at) | Q(created_at=at, pk__lt=pk))
    findings = list(qs.select_related("version__item").order_by("-created_at", "-pk")[: limit + 1])
    has_more = len(findings) > limit
    findings = findings[:limit]
    return PartnerFindingPage(
        rows=tuple(
            PartnerFindingRow(
                id=f.pk,
                item_id=f.version.item.pk,
                item_key=f.version.item.key,
                item_title=f.version.item.title,
                item_is_legacy=f.version.item.is_legacy,
                version_n=f.version.n,
                rule_id=f.rule_id,
                citation=f.citation,
                source=FindingSource(f.source),
                severity=Severity(f.severity),
                state=FindingState(f.state),
                message=f.message,
                created_at=f.created_at,
            )
            for f in findings
        ),
        next_cursor=_encode_finding_cursor(findings[-1]) if has_more and findings else None,
    )
