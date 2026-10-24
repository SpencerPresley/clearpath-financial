"""Metrics reads: load event facts and imported timelines once, measure with `metrics.measures`, aggregate.

Every number and the list of items behind it come from the same `_measure` call, so they can't disagree. The
"waiting" counts go through `reviews.selectors.filter_items` with the queue's own filters, so each equals the
queue's `?waiting=N` view (ledger stats-parity ruling).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import User
from audit.models import Event
from audit.payloads import ItemImportedPayload
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import Channel, DecisionOutcome, EventType, ItemStatus, Product, Role
from core.errors import InvalidInput
from core.permissions import require_role
from metrics.definitions import DURATION_METRICS, WAITING_THRESHOLDS, MetricBucket, MetricName, MetricSource
from metrics.measures import (
    FACT_TYPES,
    CountStat,
    DurationStat,
    Fact,
    Measurement,
    OpenClock,
    bucket_start,
    count_stat,
    duration_stat,
    imported_measurements,
    native_measurements,
    next_bucket,
)
from reviews.filters import ItemFilter
from reviews.models import QUEUE_STATUSES, ReviewItem
from reviews.selectors import filter_items

DEFAULT_DAYS = 90
MAX_ITEMS = 200


@dataclass(frozen=True)
class MetricsFilter:
    period_from: date
    period_to: date
    product: tuple[Product, ...] = ()
    channel: tuple[Channel, ...] = ()
    partner_id: tuple[int, ...] = ()
    include_legacy: bool = True

    def item_filter(self, **extra: object) -> ItemFilter:
        return ItemFilter(
            product=list(self.product),
            channel=list(self.channel),
            partner_id=list(self.partner_id),
            **extra,  # pyrefly: ignore[bad-argument-type]
        )

    def contains(self, at: datetime) -> bool:
        return self.period_from <= timezone.localdate(at) <= self.period_to


def metrics_filter(  # the query's fields
    *,
    period_from: date | None = None,
    period_to: date | None = None,
    product: Sequence[Product] = (),
    channel: Sequence[Channel] = (),
    partner_id: Sequence[int] = (),
    include_legacy: bool = True,
    clock: Clock = SYSTEM_CLOCK,
) -> MetricsFilter:
    """Defaults: the 90 days ending today."""
    to = period_to or clock.today()
    start = period_from or to - timedelta(days=DEFAULT_DAYS - 1)
    if start > to:
        raise InvalidInput.for_field("period_from", "The period starts after it ends.")
    return MetricsFilter(
        period_from=start,
        period_to=to,
        product=tuple(product),
        channel=tuple(channel),
        partner_id=tuple(partner_id),
        include_legacy=include_legacy,
    )


def _require_reader(viewer: User) -> None:
    require_role(viewer, Role.REVIEWER, Role.ADMIN)


# --- loading -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Measured:
    measurements: tuple[Measurement, ...]  # every completed measurement, any period
    open_clocks: tuple[OpenClock, ...]


def _items(viewer: User, flt: MetricsFilter, clock: Clock) -> QuerySet[ReviewItem]:
    return filter_items(viewer=viewer, filters=flt.item_filter(), clock=clock)


def _facts(items: QuerySet[ReviewItem], until: datetime) -> list[Fact]:
    rows = (
        Event.objects.filter(
            item__in=items.filter(is_legacy=False), type__in=[t.value for t in FACT_TYPES], at__lte=until
        )
        .order_by("item_id", "at", "id")
        .values_list("id", "item_id", "type", "at", "entity_id", "payload__outcome", "payload__placement_ids")
    )
    return [
        Fact(
            event_id=event_id,
            item_id=item_id,
            type=EventType(type_),
            at=at,
            entity_id=entity_id,
            outcome=DecisionOutcome(outcome) if outcome else None,
            placement_ids=tuple(placement_ids or ()),
        )
        for event_id, item_id, type_, at, entity_id, outcome, placement_ids in rows
    ]


def _imported(items: QuerySet[ReviewItem]) -> list[Measurement]:
    rows = Event.objects.filter(item__in=items.filter(is_legacy=True), type=EventType.ITEM_IMPORTED.value).values_list(
        "item_id", "payload"
    )
    out: list[Measurement] = []
    for item_id, payload in rows:
        imported = ItemImportedPayload.model_validate(payload)
        out += imported_measurements(item_id=item_id, timeline=imported.timeline)
    return out


def _measure(viewer: User, flt: MetricsFilter, clock: Clock) -> _Measured:
    """Two queries whatever the data size: native facts, then imported timelines."""
    _require_reader(viewer)
    items = _items(viewer, flt, clock)
    native, still_open = native_measurements(_facts(items, clock.now()))
    imported = _imported(items) if flt.include_legacy else []
    return _Measured(measurements=tuple(native + imported), open_clocks=tuple(still_open))


def _of(measured: _Measured, metric: MetricName, flt: MetricsFilter) -> list[Measurement]:
    return [m for m in measured.measurements if m.metric is metric and flt.contains(m.end)]


# --- summary -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ThroughputStat:
    count: int
    native_count: int
    imported_count: int
    per_week: float  # decisions per week across the period


@dataclass(frozen=True)
class OpenFixLive:
    """Live fixes still open: every fix-live clock still running (ruling 6: it stops at the approval or at the last
    confirmed takedown). `count` = `in_rereview` + `awaiting_takedown`. Only `in_rereview` is a re-review in the
    queue; pulled items whose takedown isn't confirmed are out of the queue but still unfixed (walkthrough nit 10)."""

    count: int
    in_rereview: int
    awaiting_takedown: int
    oldest_hours: float | None


@dataclass(frozen=True)
class WaitingCount:
    more_than_days: int
    count: int


@dataclass(frozen=True)
class MetricsSummary:
    period_from: date
    period_to: date
    time_to_first_review: DurationStat
    time_per_round: DurationStat
    rounds_per_item: CountStat
    time_to_fix_live: DurationStat
    open_fix_live: OpenFixLive
    throughput: ThroughputStat
    waiting: tuple[WaitingCount, ...]
    imported_from: date | None  # the span of imported history under these filters, any period
    imported_to: date | None


def _waiting(viewer: User, flt: MetricsFilter, clock: Clock) -> tuple[WaitingCount, ...]:
    """One count per threshold, each through the queue view's own filter (sort=queue, no status: the queue
    statuses, legacy excluded)."""
    queue = {"status": [ItemStatus(s) for s in QUEUE_STATUSES], "is_legacy": False}
    return tuple(
        WaitingCount(
            more_than_days=days,
            count=filter_items(
                viewer=viewer, filters=flt.item_filter(**queue, waiting_more_than_days=days), clock=clock
            ).count(),
        )
        for days in WAITING_THRESHOLDS
    )


def _hours_since(start: datetime, now: datetime) -> float:
    return (now - start).total_seconds() / 3600


def summary(*, viewer: User, flt: MetricsFilter, clock: Clock = SYSTEM_CLOCK) -> MetricsSummary:
    measured = _measure(viewer, flt, clock)
    decisions = _of(measured, MetricName.THROUGHPUT, flt)
    native_decisions = sum(1 for m in decisions if m.source is MetricSource.NATIVE)
    weeks = ((flt.period_to - flt.period_from).days + 1) / 7
    now = clock.now()
    imported_ends = [
        timezone.localdate(m.start) for m in measured.measurements if m.source is MetricSource.IMPORTED
    ] + [timezone.localdate(m.end) for m in measured.measurements if m.source is MetricSource.IMPORTED]
    return MetricsSummary(
        period_from=flt.period_from,
        period_to=flt.period_to,
        time_to_first_review=duration_stat(_of(measured, MetricName.TIME_TO_FIRST_REVIEW, flt)),
        time_per_round=duration_stat(_of(measured, MetricName.TIME_PER_ROUND, flt)),
        rounds_per_item=count_stat(_of(measured, MetricName.ROUNDS_PER_ITEM, flt)),
        time_to_fix_live=duration_stat(_of(measured, MetricName.TIME_TO_FIX_LIVE, flt)),
        open_fix_live=OpenFixLive(
            count=len(measured.open_clocks),
            in_rereview=sum(1 for c in measured.open_clocks if not c.awaiting_takedown),
            awaiting_takedown=sum(1 for c in measured.open_clocks if c.awaiting_takedown),
            oldest_hours=max((_hours_since(c.start, now) for c in measured.open_clocks), default=None),
        ),
        throughput=ThroughputStat(
            count=len(decisions),
            native_count=native_decisions,
            imported_count=len(decisions) - native_decisions,
            per_week=len(decisions) / weeks,
        ),
        waiting=_waiting(viewer, flt, clock),
        imported_from=min(imported_ends, default=None),
        imported_to=max(imported_ends, default=None),
    )


# --- series ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SeriesPoint:
    period_start: date  # the bucket's first day (a Monday, or the 1st)
    from_date: date  # the bucket clipped to the period: the drill-down range for this point
    to_date: date
    value: float | None  # median hours (durations), mean rounds, or the decision count
    native_value: float | None  # the same, per source
    imported_value: float | None
    count: int
    native_count: int
    imported_count: int


@dataclass(frozen=True)
class MetricSeries:
    metric: MetricName
    bucket: MetricBucket
    period_from: date
    period_to: date
    points: tuple[SeriesPoint, ...]


def _point_value(metric: MetricName, ms: Sequence[Measurement]) -> float | None:
    """Nothing measured is no value (a gap), except for throughput, where it is zero decisions."""
    if metric is MetricName.THROUGHPUT:
        return float(len(ms))
    if not ms:
        return None
    if metric in DURATION_METRICS:
        return duration_stat(ms).median_hours
    return count_stat(ms).mean


def series(
    *, viewer: User, metric: MetricName, bucket: MetricBucket, flt: MetricsFilter, clock: Clock = SYSTEM_CLOCK
) -> MetricSeries:
    measured = _of(_measure(viewer, flt, clock), metric, flt)
    points: list[SeriesPoint] = []
    start = bucket_start(flt.period_from, bucket)
    while start <= flt.period_to:
        end = next_bucket(start, bucket) - timedelta(days=1)
        lo, hi = max(start, flt.period_from), min(end, flt.period_to)
        inside = [m for m in measured if lo <= timezone.localdate(m.end) <= hi]
        native_ms = [m for m in inside if m.source is MetricSource.NATIVE]
        imported_ms = [m for m in inside if m.source is MetricSource.IMPORTED]
        native = len(native_ms)
        points.append(
            SeriesPoint(
                period_start=start,
                from_date=lo,
                to_date=hi,
                value=_point_value(metric, inside),
                native_value=_point_value(metric, native_ms),
                imported_value=_point_value(metric, imported_ms),
                count=len(inside),
                native_count=native,
                imported_count=len(inside) - native,
            )
        )
        start = next_bucket(start, bucket)
    return MetricSeries(
        metric=metric, bucket=bucket, period_from=flt.period_from, period_to=flt.period_to, points=tuple(points)
    )


# --- the items behind a number -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricItemRef:
    id: int
    key: str
    title: str
    status: ItemStatus
    product: Product
    channel: Channel
    is_legacy: bool
    legacy_ref: str | None
    partner_name: str | None


@dataclass(frozen=True)
class MetricItemRow:
    item: MetricItemRef
    source: MetricSource
    start: datetime
    end: datetime | None  # None for an open fix-live clock
    value: float  # as in the summary; for an open clock, hours open so far
    outcome: DecisionOutcome | None


@dataclass(frozen=True)
class MetricItems:
    metric: MetricName
    total: int
    rows: tuple[MetricItemRow, ...]  # largest value first, at most MAX_ITEMS


def metric_items(  # the query's fields
    *,
    viewer: User,
    metric: MetricName,
    flt: MetricsFilter,
    clock: Clock = SYSTEM_CLOCK,
    open_only: bool = False,
    limit: int = MAX_ITEMS,
) -> MetricItems:
    """The measurements behind a summary number or a series point (pass the point's from/to as the period).
    `open_only` (fix-live) lists the clocks still running instead."""
    measured = _measure(viewer, flt, clock)
    now = clock.now()
    if open_only:
        entries = [
            (c.item_id, MetricSource.NATIVE, c.start, None, _hours_since(c.start, now), None)
            for c in measured.open_clocks
        ]
    else:
        entries = [(m.item_id, m.source, m.start, m.end, m.value, m.outcome) for m in _of(measured, metric, flt)]
    entries.sort(key=lambda e: (-e[4], e[2]))
    shown = entries[:limit]
    items = {
        i.pk: i
        for i in ReviewItem.objects.filter(pk__in={e[0] for e in shown})
        .select_related("partner")
        .only("pk", "title", "status", "product", "channel", "is_legacy", "legacy_ref", "partner__name")
    }
    return MetricItems(
        metric=metric,
        total=len(entries),
        rows=tuple(
            MetricItemRow(
                item=MetricItemRef(
                    id=item.pk,
                    key=item.key,
                    title=item.title,
                    status=ItemStatus(item.status),
                    product=Product(item.product),
                    channel=Channel(item.channel),
                    is_legacy=item.is_legacy,
                    legacy_ref=item.legacy_ref,
                    partner_name=item.partner.name if item.partner else None,
                ),
                source=source,
                start=start,
                end=end,
                value=value,
                outcome=outcome,
            )
            for item_id, source, start, end, value, outcome in shown
            if (item := items[item_id])
        ),
    )
