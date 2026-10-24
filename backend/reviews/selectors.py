"""Reads for items. Every function returns frozen dataclasses; querysets never leave except `filter_items`,
which other selectors (export, assistant tools, search) compose with."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final

from django.db.models import BooleanField, Count, Exists, F, OuterRef, Q, QuerySet
from django.db.models.expressions import RawSQL

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    Channel,
    CheckStatus,
    ItemStatus,
    Market,
    Product,
    ReopenReason,
    RiskTier,
    TakedownState,
)
from core.errors import InvalidInput, NotFound
from reviews.filters import ItemFilter, ItemSort
from reviews.models import QUEUE_STATUSES, Placement, ReviewItem

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
    open_findings_count: int
    submitted_at: datetime
    updated_at: datetime
    age_days: int
    planned_first_run: date | None
    planned_last_run: date | None
    current_version_n: int | None
    partner: PartyRef | None
    owner: PartyRef | None
    assignee: PartyRef | None


@dataclass(frozen=True)
class ItemPage:
    rows: tuple[ItemRow, ...]
    next_cursor: str | None


def _person(user: User | None) -> PartyRef | None:
    return PartyRef(id=user.pk, name=user.display_name or user.email) if user is not None else None


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
        open_findings_count=item.open_findings_count,
        submitted_at=item.submitted_at,
        updated_at=item.updated_at,
        age_days=max((now - item.submitted_at).days, 0),
        planned_first_run=item.planned_first_run,
        planned_last_run=item.planned_last_run,
        current_version_n=getattr(item, "current_version_n", None),
        partner=PartyRef(id=partner.pk, name=partner.name) if partner is not None else None,
        owner=_person(item.owner),
        assignee=_person(item.assignee),
    )


def row_queryset(qs: QuerySet[ReviewItem]) -> QuerySet[ReviewItem]:
    """Join what a row displays in one query (no N+1)."""
    return qs.select_related("partner", "owner", "assignee").annotate(current_version_n=F("current_version__n"))


def get_item_row(*, item_id: int, clock: Clock = SYSTEM_CLOCK) -> ItemRow:
    item = row_queryset(ReviewItem.objects.filter(pk=item_id)).first()
    if item is None:
        raise NotFound.entity("item", item_id)
    return item_row(item, now=clock.now())


# Sort keys: (column, kind). Every sort ends in id so the order is total, and each sort runs one direction,
# so a page boundary is a single row-value comparison the indexes can seek to.
_SORTS: Final[dict[ItemSort, tuple[bool, tuple[tuple[str, str], ...]]]] = {
    ItemSort.QUEUE: (False, (("queue_priority", "int"), ("submitted_at", "datetime"), ("id", "int"))),
    ItemSort.OLDEST: (False, (("submitted_at", "datetime"), ("id", "int"))),
    ItemSort.NEWEST: (True, (("submitted_at", "datetime"), ("id", "int"))),
    ItemSort.UPDATED: (True, (("updated_at", "datetime"), ("id", "int"))),
    ItemSort.TITLE: (False, (("title", "str"), ("id", "int"))),
}
_TABLE: Final = ReviewItem._meta.db_table  # noqa: SLF001


def _encode_cursor(sort: ItemSort, item: ReviewItem) -> str:
    _, keys = _SORTS[sort]
    values: list[Any] = []
    for column, kind in keys:
        value = getattr(item, column)
        values.append(value.isoformat() if kind == "datetime" else value)
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
        return [
            datetime.fromisoformat(v) if kind == "datetime" else int(v) if kind == "int" else str(v)
            for v, (_, kind) in zip(values, keys, strict=True)
        ]
    except (ValueError, KeyError, TypeError) as exc:  # binascii.Error is a ValueError
        raise _bad_cursor() from exc


def list_items(
    *,
    viewer: User,
    filters: ItemFilter,
    sort: ItemSort = ItemSort.QUEUE,
    cursor: str | None = None,
    limit: int = 50,
    clock: Clock = SYSTEM_CLOCK,
) -> ItemPage:
    """One page of items in `sort` order, one query. `next_cursor` is None on the last page.

    The queue sort with no status filter means the review queue (submitted, in_review, needs_rereview), which
    is what that order is for and what the partial queue index covers. Any explicit status filter wins. That
    queue leaves out legacy imports unless `is_legacy` is set: an imported open tracker row has no version to
    review (spec §4.2 ruling 7), and `queue_stats` doesn't count them either.
    """
    descending, keys = _SORTS[sort]
    if sort is ItemSort.QUEUE and not filters.status:
        queue = {"status": [ItemStatus(s) for s in QUEUE_STATUSES]}
        filters = filters.model_copy(update=queue if filters.is_legacy is not None else {**queue, "is_legacy": False})
    qs = row_queryset(filter_items(viewer=viewer, filters=filters, clock=clock))
    if cursor is not None:
        values = _decode_cursor(sort, cursor)
        columns = ", ".join(f'"{_TABLE}"."{column}"' for column, _ in keys)
        placeholders = ", ".join(["%s"] * len(keys))
        op = "<" if descending else ">"
        qs = qs.filter(RawSQL(f"({columns}) {op} ({placeholders})", values, output_field=BooleanField()))  # noqa: S611  # identifiers are constants; values are parameters
    ordering = [f"-{column}" if descending else column for column, _ in keys]
    items = list(qs.order_by(*ordering)[: limit + 1])
    has_more = len(items) > limit
    items = items[:limit]
    now = clock.now()
    return ItemPage(
        rows=tuple(item_row(item, now=now) for item in items),
        next_cursor=_encode_cursor(sort, items[-1]) if has_more and items else None,
    )


# --- stats strip -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusCount:
    status: ItemStatus
    count: int


@dataclass(frozen=True)
class QueueStats:
    open: int  # in a reviewer's queue: submitted, in review, needs re-review
    mine: int
    unassigned: int
    needs_rereview: int
    waiting_over_3_days: int
    by_status: tuple[StatusCount, ...]


def queue_stats(*, viewer: User, clock: Clock = SYSTEM_CLOCK) -> QueueStats:
    """Counts for the stats strip, over non-legacy items."""
    current = ReviewItem.objects.filter(is_legacy=False)
    queued = Q(status__in=QUEUE_STATUSES)
    totals = current.aggregate(
        open=Count("pk", filter=queued),
        mine=Count("pk", filter=queued & Q(assignee=viewer)),
        unassigned=Count("pk", filter=queued & Q(assignee__isnull=True)),
        needs_rereview=Count("pk", filter=Q(status=ItemStatus.NEEDS_REREVIEW)),
        waiting=Count("pk", filter=queued & Q(submitted_at__lt=clock.now() - timedelta(days=3))),
    )
    by_status = {row["status"]: row["n"] for row in current.values("status").annotate(n=Count("pk"))}
    return QueueStats(
        open=totals["open"],
        mine=totals["mine"],
        unassigned=totals["unassigned"],
        needs_rereview=totals["needs_rereview"],
        waiting_over_3_days=totals["waiting"],
        by_status=tuple(StatusCount(status=s, count=by_status.get(s.value, 0)) for s in ItemStatus),
    )
