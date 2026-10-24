from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Count, Max, Q, Sum

from checks.models import Finding
from core.domain import FindingState, ItemStatus, PartnerStatus, PartnerType
from core.errors import NotFound
from partners.models import Partner
from reviews.records import AttachmentRow, list_partner_attachments


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


def get_partner_detail(*, partner_id: int) -> PartnerDetail:
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
        attachments=list_partner_attachments(partner_id=partner_id),
        repeat_issues=repeat_issues(partner_id=partner_id),
    )
