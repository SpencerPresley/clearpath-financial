"""Metrics computed from the event log plus imported history (product-spec "Metrics"; definitions in
docs/plan/screens.md). Every stat says how much of it is native and how much came from the imported tracker."""

from datetime import date, datetime

from ninja import Schema
from pydantic import Field

from core.domain import Channel, DecisionOutcome, ItemStatus, Product
from metrics.definitions import MetricBucket, MetricName, MetricSource


class MetricsQuery(Schema):
    period_from: date | None = Field(default=None, description="Defaults to 89 days before `period_to`.")
    period_to: date | None = Field(default=None, description="Defaults to today.")
    product: list[Product] = Field(default_factory=list)
    channel: list[Channel] = Field(default_factory=list)
    partner_id: list[int] = Field(default_factory=list)
    include_legacy: bool = Field(default=True, description="Count imported tracker history.")


class DurationStatOut(Schema):
    count: int
    median_hours: float | None
    p90_hours: float | None
    native_count: int
    imported_count: int


class CountStatOut(Schema):
    count: int
    mean: float | None
    median: float | None
    native_count: int
    imported_count: int


class ThroughputOut(Schema):
    count: int = Field(description="Decisions recorded in the period (imported rows: the final decision only).")
    native_count: int
    imported_count: int
    per_week: float


class OpenFixLiveOut(Schema):
    count: int = Field(description="Live content sent back for re-review and not yet fixed, now.")
    oldest_hours: float | None


class WaitingCountOut(Schema):
    more_than_days: int
    count: int = Field(description="Equals the queue's `waiting_more_than_days` view under the same filters, now.")


class MetricsSummaryOut(Schema):
    period_from: date
    period_to: date
    time_to_first_review: DurationStatOut
    time_per_round: DurationStatOut = Field(description="Native only: the tracker has no per-round dates.")
    rounds_per_item: CountStatOut
    time_to_fix_live: DurationStatOut = Field(description="Native only: imported items are never reopened.")
    open_fix_live: OpenFixLiveOut
    throughput: ThroughputOut
    waiting: list[WaitingCountOut]
    imported_from: date | None = Field(description="First date of imported history under these filters, any period.")
    imported_to: date | None


class MetricPointOut(Schema):
    period_start: date
    from_date: date = Field(description="The bucket clipped to the period; pass as the drill-down period.")
    to_date: date
    value: float | None = Field(description="Median hours (durations), mean rounds, or the decision count.")
    count: int
    native_count: int
    imported_count: int


class MetricSeriesOut(Schema):
    metric: MetricName
    bucket: MetricBucket
    period_from: date
    period_to: date
    points: list[MetricPointOut]


class MetricItemRefOut(Schema):
    id: int
    key: str = Field(examples=["CP-1042"])
    title: str
    status: ItemStatus
    product: Product
    channel: Channel
    is_legacy: bool
    legacy_ref: str | None
    partner_name: str | None


class MetricItemOut(Schema):
    item: MetricItemRefOut
    source: MetricSource
    start: datetime
    end: datetime | None = Field(description="Null for a fix-live clock still running.")
    value: float
    outcome: DecisionOutcome | None


class MetricItemsOut(Schema):
    metric: MetricName
    total: int = Field(description="Equals the number it was opened from; `rows` holds at most 200.")
    rows: list[MetricItemOut]
