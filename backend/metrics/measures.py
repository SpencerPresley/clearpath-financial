"""Metric definitions as pure functions: event facts in, measurements out (docs/plan/screens.md "Metrics").

A measurement has a start, an end, and a value; it belongs to the period containing its end. Native
measurements come from the event log; imported ones from a legacy row's `LegacyTimeline`, never from the
import event's own time.
"""

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import groupby

from audit.payloads import LegacyTimeline
from core.domain import DecisionOutcome, EventType
from metrics.definitions import MetricBucket, MetricName, MetricSource

E = EventType

ROUND_STARTS = frozenset({E.ITEM_SUBMITTED, E.ITEM_RESUBMITTED, E.ITEM_NEW_ROUND_STARTED})
APPROVING = frozenset({DecisionOutcome.APPROVED, DecisionOutcome.APPROVED_WITH_EDITS})
TERMINAL = APPROVING | {DecisionOutcome.REJECTED}
# Every event type the native measures read; the selector loads exactly these.
FACT_TYPES = frozenset(
    {
        *ROUND_STARTS,
        E.ITEM_REVIEW_STARTED,
        E.DECISION_RECORDED,
        E.ITEM_REOPENED,
        E.ITEM_WITHDRAWN,
        E.TAKEDOWN_REQUESTED,
        E.TAKEDOWN_CONFIRMED,
    }
)


@dataclass(frozen=True)
class Fact:
    """The parts of one event the measures need."""

    event_id: int
    item_id: int
    type: EventType
    at: datetime
    entity_id: int
    outcome: DecisionOutcome | None = None  # DECISION_RECORDED
    placement_ids: tuple[int, ...] = ()  # ITEM_WITHDRAWN


@dataclass(frozen=True)
class Measurement:
    metric: MetricName
    item_id: int
    source: MetricSource
    start: datetime
    end: datetime
    value: float  # hours for durations, rounds for rounds per item, 1 per decision for throughput
    outcome: DecisionOutcome | None = None  # throughput only


@dataclass(frozen=True)
class OpenClock:
    """Live content sent back for re-review and not yet fixed (approved again or taken down). `awaiting_takedown`:
    pulled (withdrawn or rejected), so out of the review queue, but a requested takedown isn't confirmed yet."""

    item_id: int
    start: datetime
    awaiting_takedown: bool = False


def _hours(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600


@dataclass
class _Episode:
    """One reopen of live content, from ITEM_REOPENED until it is fixed."""

    start: datetime
    approved_at: datetime | None = None
    pulled_at: datetime | None = None  # withdrawn or rejected
    requested: set[int] = field(default_factory=set)
    confirmed: dict[int, datetime] = field(default_factory=dict)

    def see(self, f: Fact) -> None:
        if f.type is E.DECISION_RECORDED and self.pulled_at is None and self.approved_at is None:
            if f.outcome in APPROVING:
                self.approved_at = f.at
            elif f.outcome is DecisionOutcome.REJECTED:
                self.pulled_at = f.at
        elif f.type is E.ITEM_WITHDRAWN and self.pulled_at is None and self.approved_at is None:
            self.pulled_at = f.at
            self.requested.update(f.placement_ids)
        elif f.type is E.TAKEDOWN_REQUESTED:
            self.requested.add(f.entity_id)
        elif f.type is E.TAKEDOWN_CONFIRMED:
            self.confirmed.setdefault(f.entity_id, f.at)

    def end(self) -> datetime | None:
        """Ruling 6: the fix stops at the approval, or once every requested takedown is confirmed."""
        if self.approved_at is not None:
            return self.approved_at
        if self.pulled_at is None:
            return None
        if not self.requested:
            return self.pulled_at
        if not self.requested <= self.confirmed.keys():
            return None
        return max(self.pulled_at, *(self.confirmed[p] for p in self.requested))


def _item_measurements(facts: Sequence[Fact]) -> tuple[list[Measurement], list[OpenClock]]:  # noqa: C901  # one branch per event type
    out: list[Measurement] = []
    item_id = facts[0].item_id

    def add(metric: MetricName, start: datetime, end: datetime, value: float, **extra: DecisionOutcome) -> None:
        out.append(
            Measurement(
                metric=metric, item_id=item_id, source=MetricSource.NATIVE, start=start, end=end, value=value, **extra
            )
        )

    first_submitted: datetime | None = None
    first_reviewed = False
    round_start: datetime | None = None
    cycle_start: datetime | None = None  # first round start since the last terminal decision
    cycle_rounds = 0
    episodes: list[_Episode] = []

    for f in facts:
        if f.type in ROUND_STARTS:
            first_submitted = first_submitted or f.at
            round_start = f.at
            cycle_start = cycle_start or f.at
            cycle_rounds += 1
        elif f.type is E.ITEM_REVIEW_STARTED and not first_reviewed and first_submitted is not None:
            first_reviewed = True
            add(MetricName.TIME_TO_FIRST_REVIEW, first_submitted, f.at, _hours(first_submitted, f.at))
        elif f.type is E.DECISION_RECORDED and f.outcome is not None:
            add(MetricName.THROUGHPUT, f.at, f.at, 1, outcome=f.outcome)
            if round_start is not None:
                add(MetricName.TIME_PER_ROUND, round_start, f.at, _hours(round_start, f.at))
                round_start = None
            if f.outcome in TERMINAL and cycle_start is not None:
                add(MetricName.ROUNDS_PER_ITEM, cycle_start, f.at, cycle_rounds)
                cycle_start, cycle_rounds = None, 0
        elif f.type is E.ITEM_REOPENED:
            episodes.append(_Episode(start=f.at))
            continue
        if episodes:
            episodes[-1].see(f)

    still_open: list[OpenClock] = []
    for episode in episodes:
        end = episode.end()
        if end is None:
            still_open.append(
                OpenClock(item_id=item_id, start=episode.start, awaiting_takedown=episode.pulled_at is not None)
            )
        else:
            add(MetricName.TIME_TO_FIX_LIVE, episode.start, end, _hours(episode.start, end))
    return out, still_open


def native_measurements(facts: Iterable[Fact]) -> tuple[list[Measurement], list[OpenClock]]:
    """Measurements and still-open fix-live clocks. `facts` must be ordered by (item_id, at, event_id)."""
    measured: list[Measurement] = []
    still_open: list[OpenClock] = []
    for _, group in groupby(facts, key=lambda f: f.item_id):
        m, o = _item_measurements(list(group))
        measured += m
        still_open += o
    return measured, still_open


def imported_measurements(*, item_id: int, timeline: LegacyTimeline) -> list[Measurement]:
    """What a tracker row can honestly say: first review (first reviewer comment), rounds and the final decision.
    It has no per-round dates and no reopens, so no round times and no fix-live times."""
    out: list[Measurement] = []

    def add(metric: MetricName, start: datetime, end: datetime, value: float, **extra: DecisionOutcome) -> None:
        out.append(
            Measurement(
                metric=metric, item_id=item_id, source=MetricSource.IMPORTED, start=start, end=end, value=value, **extra
            )
        )

    t = timeline
    if t.submitted_at is not None and t.first_reviewed_at is not None:
        add(
            MetricName.TIME_TO_FIRST_REVIEW,
            t.submitted_at,
            t.first_reviewed_at,
            _hours(t.submitted_at, t.first_reviewed_at),
        )
    if t.decided_at is not None and t.outcome is not None:
        if t.outcome in TERMINAL and t.rounds is not None:
            add(MetricName.ROUNDS_PER_ITEM, t.submitted_at or t.decided_at, t.decided_at, t.rounds)
        add(MetricName.THROUGHPUT, t.decided_at, t.decided_at, 1, outcome=t.outcome)
    return out


# --- aggregation -------------------------------------------------------------------------------------------------


def percentile(values: Sequence[float], q: float) -> float:
    """Linear interpolation between order statistics, as Postgres `percentile_cont` computes it."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _values(measurements: Sequence[Measurement], source: MetricSource | None = None) -> list[float]:
    return [m.value for m in measurements if source is None or m.source is source]


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


@dataclass(frozen=True)
class DurationStat:
    count: int
    median_hours: float | None
    p90_hours: float | None
    native_count: int
    imported_count: int
    # Per source: a blended median hides the tracker-era vs in-app difference.
    native_median_hours: float | None
    imported_median_hours: float | None


def duration_stat(measurements: Sequence[Measurement]) -> DurationStat:
    values = _values(measurements)
    native = _values(measurements, MetricSource.NATIVE)
    imported = _values(measurements, MetricSource.IMPORTED)
    return DurationStat(
        count=len(values),
        median_hours=_median(values),
        p90_hours=percentile(values, 0.9) if values else None,
        native_count=len(native),
        imported_count=len(imported),
        native_median_hours=_median(native),
        imported_median_hours=_median(imported),
    )


@dataclass(frozen=True)
class CountStat:
    count: int
    mean: float | None
    median: float | None
    native_count: int
    imported_count: int
    native_mean: float | None
    imported_mean: float | None


def count_stat(measurements: Sequence[Measurement]) -> CountStat:
    values = _values(measurements)
    native = _values(measurements, MetricSource.NATIVE)
    imported = _values(measurements, MetricSource.IMPORTED)
    return CountStat(
        count=len(values),
        mean=_mean(values),
        median=_median(values),
        native_count=len(native),
        imported_count=len(imported),
        native_mean=_mean(native),
        imported_mean=_mean(imported),
    )


def bucket_start(on: date, bucket: MetricBucket) -> date:
    """Weeks start on Monday."""
    if bucket is MetricBucket.WEEK:
        return on - timedelta(days=on.weekday())
    return on.replace(day=1)


def next_bucket(start: date, bucket: MetricBucket) -> date:
    if bucket is MetricBucket.WEEK:
        return start + timedelta(days=7)
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
