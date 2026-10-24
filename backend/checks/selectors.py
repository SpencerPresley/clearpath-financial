from dataclasses import dataclass
from datetime import datetime

from django.db.models import QuerySet

from checks.models import Finding
from core.domain import FindingSource, FindingState, FixKind, Severity
from core.errors import NotFound
from reviews.models import ReviewItem
from reviews.records import Span
from reviews.selectors import PartyRef


@dataclass(frozen=True)
class FindingRow:
    id: int
    version_n: int
    rule_id: str
    citation: str
    source: FindingSource
    severity: Severity
    state: FindingState
    span: Span | None
    quote: str | None
    message: str
    suggested_fix: str
    fix_kind: FixKind | None  # None: unknown (recorded before fix kinds) or no fix
    replacement_text: str | None
    reason: str
    resolved_by: PartyRef | None
    resolved_at: datetime | None
    carried_from_id: int | None
    created_at: datetime


def _rows(qs: QuerySet[Finding]) -> QuerySet[Finding]:
    return qs.select_related("resolved_by", "version").defer("version__content_text", "version__search_vector")


def _row(f: Finding) -> FindingRow:
    return FindingRow(
        id=f.pk,
        version_n=f.version.n,
        rule_id=f.rule_id,
        citation=f.citation,
        source=FindingSource(f.source),
        severity=Severity(f.severity),
        state=FindingState(f.state),
        span=Span(f.span_start, f.span_end) if f.span_start is not None and f.span_end is not None else None,
        quote=f.quote,
        message=f.message,
        suggested_fix=f.suggested_fix,
        fix_kind=FixKind(f.fix_kind) if f.fix_kind else None,
        replacement_text=f.replacement_text,
        reason=f.reason,
        resolved_by=PartyRef(id=f.resolved_by.pk, name=f.resolved_by.display_name or f.resolved_by.email)
        if f.resolved_by
        else None,
        resolved_at=f.resolved_at,
        carried_from_id=f.carried_from_id,  # pyrefly: ignore[missing-attribute]
        created_at=f.created_at,
    )


def list_findings(*, item_id: int, version_n: int | None = None) -> tuple[FindingRow, ...]:
    """Findings for the item's current version (or `version_n`), blocking first, then by position."""
    item = (
        ReviewItem.objects.filter(pk=item_id).select_related("current_version").only("pk", "current_version__n").first()
    )
    if item is None:
        raise NotFound.entity("item", item_id)
    n = version_n if version_n is not None else (item.current_version.n if item.current_version else None)
    if n is None:
        return ()
    qs = _rows(Finding.objects.filter(version__item_id=item_id, version__n=n)).order_by("severity", "span_start", "pk")
    return tuple(_row(f) for f in qs)


def get_finding(*, finding_id: int) -> FindingRow:
    finding = _rows(Finding.objects.filter(pk=finding_id)).first()
    if finding is None:
        raise NotFound.entity("finding", finding_id)
    return _row(finding)
