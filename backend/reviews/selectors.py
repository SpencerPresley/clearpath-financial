"""Reads for items. Every function returns frozen dataclasses; querysets never leave except `filter_items` and
`view_items`, which other selectors (export, assistant tools, search) compose with."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any, Final, Literal

from django.db.models import (
    Case,
    CharField,
    Count,
    Exists,
    Expression,
    F,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.fields.tuple_lookups import Tuple, TupleGreaterThan, TupleLessThan
from django.db.models.functions import Coalesce, Lower, NullIf

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    Channel,
    CheckStatus,
    DecisionOutcome,
    ItemStatus,
    Market,
    Product,
    ReopenReason,
    RiskTier,
    TakedownState,
)
from core.errors import InvalidInput, NotFound
from reviews.filters import ItemFilter, ItemSort
from reviews.models import APPROVED_OUTCOMES, QUEUE_STATUSES, Decision, Placement, ReviewItem

_KEY = re.compile(r"^\s*CP-(\d+)\s*$", re.IGNORECASE)


# --- liveness --------------------------------------------------------------------------------------------------


def live_placements_q(today: date, prefix: str = "") -> Q:
    """Placements running today with no confirmed takedown (spec §4.2 ruling 2). `prefix` lets callers
    apply it through a relation, e.g. `live_placements_q(today, "placements__")`."""
    p = prefix
    return (
        Q(**{f"{p}first_run__lte": today})
        & (Q(**{f"{p}last_run__isnull": True}) | Q(**{f"{p}last_run__gte": today}))
        & ~Q(**{f"{p}takedown_state": TakedownState.CONFIRMED.value})
    )


def is_item_live(*, item_id: int, today: date) -> bool:
    """Whether the item's content is running today (ruling 2): decides needs_rereview vs expired."""
    return Placement.objects.filter(live_placements_q(today), item_id=item_id).exists()


# --- filtering -------------------------------------------------------------------------------------------------


def _in_range(
    qs: QuerySet[ReviewItem], field: str, after: datetime | None, before: datetime | None
) -> QuerySet[ReviewItem]:
    """`after <= field < before`, each bound optional."""
    if after:
        qs = qs.filter(**{f"{field}__gte": after})
    if before:
        qs = qs.filter(**{f"{field}__lt": before})
    return qs


def filter_items(*, viewer: User, filters: ItemFilter, clock: Clock = SYSTEM_CLOCK) -> QuerySet[ReviewItem]:  # noqa: C901, PLR0912  # one branch per filter field
    qs = ReviewItem.objects.all()
    f = filters
    if f.q:
        key = _KEY.match(f.q)
        qs = qs.filter(pk=int(key.group(1))) if key else qs.filter(title__icontains=f.q.strip())
    if f.status:
        qs = qs.filter(status__in=f.status)
    if f.product:
        qs = qs.filter(product__in=f.product)
    if f.channel:
        qs = qs.filter(channel__in=f.channel)
    if f.partner_id:
        qs = qs.filter(partner_id__in=f.partner_id)
    if f.assignee_id:
        qs = qs.filter(assignee_id__in=f.assignee_id)
    if f.owner_id:
        qs = qs.filter(owner_id__in=f.owner_id)
    if f.mine:
        qs = qs.filter(assignee=viewer)
    if f.submitted_by_me:
        qs = qs.filter(owner=viewer)
    if f.unassigned:
        qs = qs.filter(assignee__isnull=True)
    if f.risk_tier:
        qs = qs.filter(risk_tier__in=f.risk_tier)
    if f.market:
        qs = qs.filter(markets__overlap=list(f.market))
    if f.tag:
        qs = qs.filter(tags__contains=list(f.tag))
    if f.is_legacy is not None:
        qs = qs.filter(is_legacy=f.is_legacy)
    if f.has_open_findings is not None:
        qs = qs.filter(open_findings_count__gt=0) if f.has_open_findings else qs.filter(open_findings_count=0)
    if f.reopen_reason:
        qs = qs.filter(reopen_reason__in=f.reopen_reason)
    qs = _in_range(qs, "submitted_at", f.submitted_after, f.submitted_before)
    if f.waiting_more_than_days is not None:
        qs = qs.filter(submitted_at__lt=clock.now() - timedelta(days=f.waiting_more_than_days))
    qs = _in_range(qs, "approved_at", f.approved_after, f.approved_before)
    if f.approved_within_days is not None:
        qs = qs.filter(approved_at__gte=clock.now() - timedelta(days=f.approved_within_days))
    if f.run_from or f.run_to:
        runs = Placement.objects.filter(item=OuterRef("pk"))
        if f.run_to:
            runs = runs.filter(first_run__lte=f.run_to)
        if f.run_from:
            runs = runs.filter(Q(last_run__isnull=True) | Q(last_run__gte=f.run_from))
        qs = qs.filter(Exists(runs))
    return qs


# --- rows and keyset pagination --------------------------------------------------------------------------------


@dataclass(frozen=True)
class PartyRef:
    """A person or partner as shown in a cell: id plus display name."""

    id: int
    name: str


@dataclass(frozen=True)
class DecisionSummary:
    """The item's latest decision, as a row shows it. `records.DecisionRow` is the full record."""

    outcome: DecisionOutcome
    reason: str
    decided_at: datetime
    approver: PartyRef


@dataclass(frozen=True)
class ItemRow:
    id: int
    key: str
    title: str
    product: Product
    channel: Channel
    status: ItemStatus
    round: int
    risk_tier: RiskTier
    reopen_reason: ReopenReason | None
    llm_check_status: CheckStatus
    is_legacy: bool
    markets: tuple[Market, ...]
    tags: tuple[str, ...]
    notes: str
    open_findings_count: int
    submitted_at: datetime
    updated_at: datetime
    age_days: int
    planned_first_run: date | None
    planned_last_run: date | None
    current_version_n: int | None
    # The latest approval's expiry. Written with each approval and kept after it lapses or is reopened (the
    # review screen says "Approval expired <date>"); null if the item was never approved.
    approval_expires_at: datetime | None
    latest_decision: DecisionSummary | None
    partner: PartyRef | None
    owner: PartyRef | None
    assignee: PartyRef | None


@dataclass(frozen=True)
class ItemPage:
    rows: tuple[ItemRow, ...]
    next_cursor: str | None
    total: int  # every row the filters match, not just this page


def _person(user: User | None) -> PartyRef | None:
    return PartyRef(id=user.pk, name=user.display_name or user.email) if user is not None else None


def _latest_decision(item: ReviewItem) -> DecisionSummary | None:
    outcome = getattr(item, "latest_decision_outcome", None)
    if outcome is None:
        return None
    return DecisionSummary(
        outcome=DecisionOutcome(outcome),
        reason=item.latest_decision_reason,  # pyrefly: ignore[missing-attribute]  # row_queryset annotation
        decided_at=item.latest_decision_at,  # pyrefly: ignore[missing-attribute]
        approver=PartyRef(
            id=item.latest_decision_approver_id,  # pyrefly: ignore[missing-attribute]
            name=item.latest_decision_approver_name,  # pyrefly: ignore[missing-attribute]
        ),
    )


def item_row(item: ReviewItem, *, now: datetime) -> ItemRow:
    """Build a row from an item fetched with `row_queryset` (relations already joined)."""
    partner = item.partner
    return ItemRow(
        id=item.pk,
        key=item.key,
        title=item.title,
        product=Product(item.product),
        channel=Channel(item.channel),
        status=ItemStatus(item.status),
        round=item.round,
        risk_tier=RiskTier(item.risk_tier),
        reopen_reason=ReopenReason(item.reopen_reason) if item.reopen_reason else None,
        llm_check_status=CheckStatus(item.llm_check_status),
        is_legacy=item.is_legacy,
        markets=tuple(Market(m) for m in item.markets),
        tags=tuple(item.tags),
        notes=item.notes,
        open_findings_count=item.open_findings_count,
        submitted_at=item.submitted_at,
        updated_at=item.updated_at,
        age_days=max((now - item.submitted_at).days, 0),
        planned_first_run=item.planned_first_run,
        planned_last_run=item.planned_last_run,
        current_version_n=getattr(item, "current_version_n", None),
        approval_expires_at=item.approval_expires_at,
        latest_decision=_latest_decision(item),
        partner=PartyRef(id=partner.pk, name=partner.name) if partner is not None else None,
        owner=_person(item.owner),
        assignee=_person(item.assignee),
    )


def _display_name(user: str) -> Coalesce:
    """The name a cell shows for the user at relation `user` (as `_person`): display name, else email."""
    return Coalesce(NullIf(F(f"{user}__display_name"), Value("")), F(f"{user}__email"), output_field=CharField())


def _latest_decision_field(field: str | Expression) -> Subquery:
    # Same order as records' decision list, so a row and the item's detail agree on which one is latest.
    latest = Decision.objects.filter(item=OuterRef("pk")).order_by("-decided_at", "-pk")
    if not isinstance(field, str):
        latest, field = latest.annotate(value=field), "value"
    return Subquery(latest.values(field)[:1])


def row_queryset(qs: QuerySet[ReviewItem]) -> QuerySet[ReviewItem]:
    """Join what a row displays in one query (no N+1). The latest decision is five correlated lookups on
    `decision_item_idx`, evaluated for the rows returned."""
    return qs.select_related("partner", "owner", "assignee").annotate(
        current_version_n=F("current_version__n"),
        latest_decision_outcome=_latest_decision_field("outcome"),
        latest_decision_reason=_latest_decision_field("reason"),
        latest_decision_at=_latest_decision_field("decided_at"),
        latest_decision_approver_id=_latest_decision_field("approver_id"),
        latest_decision_approver_name=_latest_decision_field(_display_name("approver")),
    )


def get_item_row(*, item_id: int, clock: Clock = SYSTEM_CLOCK) -> ItemRow:
    item = row_queryset(ReviewItem.objects.filter(pk=item_id)).first()
    if item is None:
        raise NotFound.entity("item", item_id)
    return item_row(item, now=clock.now())


# --- sorting and keyset pagination -----------------------------------------------------------------------------


@dataclass(frozen=True)
class _Key:
    """One sort key: a column, or an expression annotated under `name`. `kind` is how a cursor stores it."""

    name: str
    kind: Literal["int", "str", "datetime"]
    expression: Expression | None = None


def _rank(field: str, order: tuple[StrEnum, ...]) -> Case:
    return Case(
        *(When(**{field: member.value}, then=Value(i)) for i, member in enumerate(order)),
        default=Value(len(order)),
        output_field=IntegerField(),
    )


def _by_name(relation: str, name: Expression | F) -> tuple[_Key, _Key]:
    """Rows without the relation sort after every name (before them when descending), like NULLS LAST. The
    name is never NULL: `(NULL, 7) > ('', 5)` is NULL in SQL, which would end the walk at that page."""
    missing = Case(When(**{f"{relation}__isnull": True}, then=Value(1)), default=Value(0), output_field=IntegerField())
    return (
        _Key(f"sort_{relation}_missing", "int", missing),
        _Key(f"sort_{relation}_name", "str", Lower(Coalesce(name, Value("")))),
    )


# The board's column order, then the ends of the line.
STATUS_ORDER: Final = (
    ItemStatus.DRAFT,
    ItemStatus.SUBMITTED,
    ItemStatus.IN_REVIEW,
    ItemStatus.CHANGES_REQUESTED,
    ItemStatus.NEEDS_REREVIEW,
    ItemStatus.APPROVED,
    ItemStatus.EXPIRED,
    ItemStatus.WITHDRAWN,
    ItemStatus.REJECTED,
)
RISK_ORDER: Final = (RiskTier.LOW, RiskTier.MEDIUM, RiskTier.HIGH)

_ID: Final = _Key("id", "int")
_SUBMITTED: Final = _Key("submitted_at", "datetime")
_COLUMN_SORTS: Final[dict[tuple[ItemSort, ItemSort], tuple[_Key, ...]]] = {
    (ItemSort.TITLE, ItemSort.TITLE_DESC): (_Key("title", "str"), _ID),
    (ItemSort.STATUS, ItemSort.STATUS_DESC): (_Key("sort_status", "int", _rank("status", STATUS_ORDER)), _ID),
    (ItemSort.RISK_TIER, ItemSort.RISK_TIER_DESC): (_Key("sort_risk", "int", _rank("risk_tier", RISK_ORDER)), _ID),
    (ItemSort.ASSIGNEE, ItemSort.ASSIGNEE_DESC): (*_by_name("assignee", _display_name("assignee")), _ID),
    (ItemSort.PARTNER, ItemSort.PARTNER_DESC): (*_by_name("partner", F("partner__name")), _ID),
    (ItemSort.OPEN_FINDINGS, ItemSort.OPEN_FINDINGS_DESC): (_Key("open_findings_count", "int"), _ID),
    (ItemSort.ROUND, ItemSort.ROUND_DESC): (_Key("round", "int"), _ID),
}

# (descending, keys). Every sort ends in id so the order is total, and each runs one direction (every key the
# same way), so a page boundary is a single row-value comparison; for the queue, one the index can seek to.
_SORTS: Final[dict[ItemSort, tuple[bool, tuple[_Key, ...]]]] = {
    ItemSort.QUEUE: (False, (_Key("queue_priority", "int"), _SUBMITTED, _ID)),
    ItemSort.OLDEST: (False, (_SUBMITTED, _ID)),
    ItemSort.NEWEST: (True, (_SUBMITTED, _ID)),
    ItemSort.UPDATED: (True, (_Key("updated_at", "datetime"), _ID)),
    **{asc: (False, keys) for (asc, _), keys in _COLUMN_SORTS.items()},
    **{desc: (True, keys) for (_, desc), keys in _COLUMN_SORTS.items()},
}


def sort_items(qs: QuerySet[ReviewItem], sort: ItemSort) -> QuerySet[ReviewItem]:
    """`qs` in `sort` order (annotating the keys that aren't columns)."""
    descending, keys = _SORTS[sort]
    annotations = {key.name: key.expression for key in keys if key.expression is not None}
    return qs.annotate(**annotations).order_by(*(f"-{key.name}" if descending else key.name for key in keys))


def _encode_cursor(sort: ItemSort, item: ReviewItem) -> str:
    _, keys = _SORTS[sort]
    values: list[Any] = []
    for key in keys:
        value = getattr(item, key.name)
        values.append(value.isoformat() if key.kind == "datetime" else value)
    raw = json.dumps({"s": sort.value, "v": values}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _bad_cursor() -> InvalidInput:
    return InvalidInput(
        "This page link is out of date. Reload the list.",
        fields=[],
        details={"field": "cursor"},
    )


def _decode_cursor(sort: ItemSort, cursor: str) -> list[Any]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if data["s"] != sort.value:
            raise _bad_cursor()
        _, keys = _SORTS[sort]
        values: list[Any] = data["v"]
        if len(values) != len(keys):
            raise _bad_cursor()
        decoded = [
            datetime.fromisoformat(v) if key.kind == "datetime" else int(v) if key.kind == "int" else str(v)
            for v, key in zip(values, keys, strict=True)
        ]
    except (ValueError, KeyError, TypeError) as exc:  # binascii.Error is a ValueError
        raise _bad_cursor() from exc
    if any(isinstance(v, str) and "\x00" in v for v in decoded):  # no column holds one; Postgres refuses it
        raise _bad_cursor()
    return decoded


def _scoped(filters: ItemFilter, sort: ItemSort) -> ItemFilter:
    """The queue sort with no status filter means the review queue (submitted, in_review, needs_rereview),
    which is what that order is for and what the partial queue index covers. Any explicit status filter wins.
    That queue leaves out legacy imports unless `is_legacy` is set: an imported open tracker row has no version
    to review (spec §4.2 ruling 7)."""
    if sort is not ItemSort.QUEUE or filters.status:
        return filters
    queue = {"status": [ItemStatus(s) for s in QUEUE_STATUSES]}
    return filters.model_copy(update=queue if filters.is_legacy is not None else {**queue, "is_legacy": False})


def view_items(
    *, viewer: User, filters: ItemFilter, sort: ItemSort, clock: Clock = SYSTEM_CLOCK
) -> QuerySet[ReviewItem]:
    """Every row `list_items` would page through, in its order: what an export of the view contains."""
    return sort_items(filter_items(viewer=viewer, filters=_scoped(filters, sort), clock=clock), sort)


def list_items(
    *,
    viewer: User,
    filters: ItemFilter,
    sort: ItemSort = ItemSort.QUEUE,
    cursor: str | None = None,
    limit: int = 50,
    clock: Clock = SYSTEM_CLOCK,
) -> ItemPage:
    """One page of items in `sort` order, plus the total: two queries. `next_cursor` is None on the last page.
    See `_scoped` for what the queue sort means without a status filter."""
    qs = filter_items(viewer=viewer, filters=_scoped(filters, sort), clock=clock)
    return _page(qs, sort=sort, cursor=cursor, limit=limit, clock=clock)


def _page(qs: QuerySet[ReviewItem], *, sort: ItemSort, cursor: str | None, limit: int, clock: Clock) -> ItemPage:
    total = qs.count()  # one COUNT over the filtered set; fine at our scale
    descending, keys = _SORTS[sort]
    qs = sort_items(row_queryset(qs), sort)
    if cursor is not None:
        after = TupleLessThan if descending else TupleGreaterThan
        qs = qs.filter(after(Tuple(*(F(key.name) for key in keys)), _decode_cursor(sort, cursor)))
    items = list(qs[: limit + 1])
    has_more = len(items) > limit
    items = items[:limit]
    now = clock.now()
    return ItemPage(
        rows=tuple(item_row(item, now=now) for item in items),
        next_cursor=_encode_cursor(sort, items[-1]) if has_more and items else None,
        total=total,
    )


# --- library ---------------------------------------------------------------------------------------------------


class LibraryScope(StrEnum):
    """The library's two views (ledger ruling): what may run now, and every approval ever given (precedent value
    doesn't lapse; run-permission does)."""

    APPROVED_TO_RUN = "approved_to_run"  # current status approved, legacy included
    EVER_APPROVED = "ever_approved"  # any approving decision, or an imported item the tracker had as approved


def library_items(  # list_items' arguments plus the scope
    *,
    viewer: User,
    filters: ItemFilter,
    scope: LibraryScope = LibraryScope.APPROVED_TO_RUN,
    sort: ItemSort = ItemSort.UPDATED,
    cursor: str | None = None,
    limit: int = 50,
    clock: Clock = SYSTEM_CLOCK,
) -> ItemPage:
    """The approved archive. `filters.status` narrows within the scope (e.g. ever-approved items now expired)."""
    qs = filter_items(viewer=viewer, filters=filters, clock=clock)
    if scope is LibraryScope.APPROVED_TO_RUN:
        qs = qs.filter(status=ItemStatus.APPROVED.value)
    else:
        approvals = Decision.objects.filter(item=OuterRef("pk"), outcome__in=APPROVED_OUTCOMES)
        qs = qs.filter(Exists(approvals) | Q(is_legacy=True, status=ItemStatus.APPROVED.value))
    return _page(qs, sort=sort, cursor=cursor, limit=limit, clock=clock)


# --- stats strip -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusCount:
    status: ItemStatus
    count: int
    filters: ItemFilter  # the view this count is the total of


@dataclass(frozen=True)
class QueueStatFilters:
    """Each stat's definition, as the view that lists exactly the items it counts. Every one names its
    statuses and excludes legacy imports explicitly, so the set doesn't depend on the sort it's shown in."""

    open: ItemFilter  # in a reviewer's queue: submitted, in review, needs re-review
    mine: ItemFilter
    unassigned: ItemFilter
    needs_rereview: ItemFilter  # status needs_rereview; a re-review a reviewer has opened is in review
    waiting_over_3_days: ItemFilter


def queue_stat_filters() -> QueueStatFilters:
    queue = [ItemStatus(s) for s in QUEUE_STATUSES]
    return QueueStatFilters(
        open=ItemFilter(status=queue, is_legacy=False),
        mine=ItemFilter(status=queue, is_legacy=False, mine=True),
        unassigned=ItemFilter(status=queue, is_legacy=False, unassigned=True),
        needs_rereview=ItemFilter(status=[ItemStatus.NEEDS_REREVIEW], is_legacy=False),
        waiting_over_3_days=ItemFilter(status=queue, is_legacy=False, waiting_more_than_days=3),
    )


@dataclass(frozen=True)
class QueueStats:
    open: int
    mine: int
    unassigned: int
    needs_rereview: int
    waiting_over_3_days: int
    by_status: tuple[StatusCount, ...]  # non-legacy items in each status
    filters: QueueStatFilters


def queue_stats(*, viewer: User, clock: Clock = SYSTEM_CLOCK) -> QueueStats:
    """Counts for the stats strip. Each is counted through `filter_items` with the filter it exports, so it
    equals `list_items(filters=that).total` by construction. Two queries."""
    definitions = queue_stat_filters()
    names = [f.name for f in fields(QueueStatFilters)]
    totals = ReviewItem.objects.aggregate(
        **{
            name: Count(
                "pk",
                filter=Q(
                    pk__in=filter_items(viewer=viewer, filters=getattr(definitions, name), clock=clock).values("pk")
                ),
            )
            for name in names
        }
    )
    current = filter_items(viewer=viewer, filters=ItemFilter(is_legacy=False), clock=clock)
    by_status = {row["status"]: row["n"] for row in current.values("status").annotate(n=Count("pk"))}
    return QueueStats(
        open=totals["open"],
        mine=totals["mine"],
        unassigned=totals["unassigned"],
        needs_rereview=totals["needs_rereview"],
        waiting_over_3_days=totals["waiting_over_3_days"],
        by_status=tuple(
            StatusCount(status=s, count=by_status.get(s.value, 0), filters=ItemFilter(status=[s], is_legacy=False))
            for s in ItemStatus
        ),
        filters=definitions,
    )
