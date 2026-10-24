"""Metrics computed from the event log plus imported history (product-spec "Metrics")."""

from datetime import date
from enum import StrEnum

from ninja import Schema
from pydantic import Field

from core.domain import Channel, Product


class MetricName(StrEnum):
    TIME_TO_FIRST_REVIEW = "time_to_first_review"
    TIME_PER_ROUND = "time_per_round"
    ROUNDS_PER_ITEM = "rounds_per_item"
    TIME_TO_FIX_LIVE = "time_to_fix_live"
    AGED_ITEMS = "aged_items"


class MetricBucket(StrEnum):
    WEEK = "week"
    MONTH = "month"


class MetricsQuery(Schema):
    period_from: date | None = Field(default=None, description="Defaults to 90 days ago.")
    period_to: date | None = Field(default=None, description="Defaults to today.")
    product: list[Product] = Field(default_factory=list)
    channel: list[Channel] = Field(default_factory=list)
    include_legacy: bool = True


class DurationStatOut(Schema):
    count: int
    median_hours: float | None
    p90_hours: float | None


class CountStatOut(Schema):
    count: int
    mean: float | None
    median: float | None


class AgedBucketOut(Schema):
    label: str = Field(examples=["3-7 days"])
    min_days: int
    max_days: int | None
    count: int


class MetricsSummaryOut(Schema):
    period_from: date
    period_to: date
    time_to_first_review: DurationStatOut
    time_per_round: DurationStatOut
    rounds_per_item: CountStatOut
    time_to_fix_live: DurationStatOut
    aged_items: list[AgedBucketOut]


class MetricPointOut(Schema):
    period_start: date
    value: float | None
    count: int


class MetricSeriesOut(Schema):
    metric: MetricName
    bucket: MetricBucket
    points: list[MetricPointOut]
