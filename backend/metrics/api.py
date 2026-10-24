from django.http import HttpRequest
from ninja import Query, Router

from accounts.api import current_user
from core.schemas import ERRORS
from metrics import selectors
from metrics.schemas import MetricBucket, MetricItemsOut, MetricName, MetricSeriesOut, MetricsQuery, MetricsSummaryOut

router = Router(tags=["metrics"])


def _filter(query: MetricsQuery) -> selectors.MetricsFilter:
    return selectors.metrics_filter(
        period_from=query.period_from,
        period_to=query.period_to,
        product=query.product,
        channel=query.channel,
        partner_id=query.partner_id,
        include_legacy=query.include_legacy,
    )


@router.get("/metrics/summary", response={200: MetricsSummaryOut, **ERRORS}, operation_id="getMetricsSummary")
def summary(request: HttpRequest, query: Query[MetricsQuery]) -> selectors.MetricsSummary:
    """Headline numbers for the period. Reviewers, leads, admins."""
    return selectors.summary(viewer=current_user(request), flt=_filter(query))


@router.get("/metrics/series", response={200: MetricSeriesOut, **ERRORS}, operation_id="getMetricSeries")
def series(
    request: HttpRequest, metric: MetricName, query: Query[MetricsQuery], bucket: MetricBucket = MetricBucket.WEEK
) -> selectors.MetricSeries:
    """One metric per week or month, empty buckets included; each point's `from_date`/`to_date` open its items."""
    return selectors.series(viewer=current_user(request), metric=metric, bucket=bucket, flt=_filter(query))


@router.get("/metrics/items", response={200: MetricItemsOut, **ERRORS}, operation_id="listMetricItems")
def items(
    request: HttpRequest, metric: MetricName, query: Query[MetricsQuery], open_only: bool = False
) -> selectors.MetricItems:
    """The measurements behind a number: same computation, so `total` equals the number. `open_only` with
    `time_to_fix_live` lists the clocks still running."""
    return selectors.metric_items(viewer=current_user(request), metric=metric, flt=_filter(query), open_only=open_only)
