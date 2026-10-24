from django.http import HttpRequest
from ninja import Query, Router

from core.errors import NotImplementedYet
from core.schemas import STUB_ERRORS
from metrics.schemas import MetricBucket, MetricName, MetricSeriesOut, MetricsQuery, MetricsSummaryOut

router = Router(tags=["metrics"])


@router.get("/metrics/summary", response={200: MetricsSummaryOut, **STUB_ERRORS}, operation_id="getMetricsSummary")
def summary(request: HttpRequest, query: Query[MetricsQuery]) -> MetricsSummaryOut:
    """The stats strip and metrics page headline numbers. [metrics owner: see ledger]"""
    raise NotImplementedYet("metrics")


@router.get("/metrics/series", response={200: MetricSeriesOut, **STUB_ERRORS}, operation_id="getMetricSeries")
def series(
    request: HttpRequest, metric: MetricName, query: Query[MetricsQuery], bucket: MetricBucket = MetricBucket.WEEK
) -> MetricSeriesOut:
    """[metrics owner: see ledger]"""
    raise NotImplementedYet("metrics")
