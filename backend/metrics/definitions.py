"""Metric vocabulary shared by the pure measures, the selectors, and the API schemas."""

from enum import StrEnum


class MetricName(StrEnum):
    TIME_TO_FIRST_REVIEW = "time_to_first_review"
    TIME_PER_ROUND = "time_per_round"
    ROUNDS_PER_ITEM = "rounds_per_item"
    TIME_TO_FIX_LIVE = "time_to_fix_live"
    THROUGHPUT = "throughput"


DURATION_METRICS = frozenset({MetricName.TIME_TO_FIRST_REVIEW, MetricName.TIME_PER_ROUND, MetricName.TIME_TO_FIX_LIVE})


class MetricBucket(StrEnum):
    WEEK = "week"
    MONTH = "month"


class MetricSource(StrEnum):
    """Where a measurement came from: this app's event log, or a legacy tracker row's own dates."""

    NATIVE = "native"
    IMPORTED = "imported"


# "Items waiting more than N days": each threshold is the queue's `?waiting=N` view.
WAITING_THRESHOLDS: tuple[int, ...] = (3, 7, 14, 30)
