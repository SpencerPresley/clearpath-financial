"""Metrics over real events: items driven through the review services, plus imported tracker rows."""

from datetime import date, timedelta

import pytest

from accounts.models import User
from core.clock import FixedClock
from core.domain import Channel, DecisionOutcome, ItemStatus, Product, ReopenReason
from core.errors import InvalidInput, NotPermitted
from metrics import selectors
from metrics.definitions import MetricBucket, MetricName, MetricSource
from metrics.selectors import MetricsFilter
from metrics.tests.conftest import import_row
from reviews.filters import ItemFilter
from reviews.models import ReviewItem
from reviews.selectors import list_items

pytestmark = pytest.mark.django_db

M = MetricName


def window(clock: FixedClock, days: int = 30, **kw: object) -> MetricsFilter:
    return MetricsFilter(period_from=clock.today() - timedelta(days=days), period_to=clock.today(), **kw)  # pyrefly: ignore[bad-argument-type]


def test_two_round_item_through_the_services(two_round_item: ReviewItem, lead: User, clock: FixedClock) -> None:
    summary = selectors.summary(viewer=lead, flt=window(clock), clock=clock)

    assert (summary.time_to_first_review.count, summary.time_to_first_review.median_hours) == (1, 5)
    assert summary.time_per_round.count == 2
    assert summary.time_per_round.median_hours == pytest.approx(6)  # rounds of 8h and 4h
    assert (summary.rounds_per_item.count, summary.rounds_per_item.mean) == (1, 2)
    assert summary.throughput.count == 2
    assert summary.throughput.native_count == 2


def test_imported_rows_count_where_the_tracker_has_the_dates(lead: User, clock: FixedClock) -> None:
    import_row(
        "MCR-26-001",
        submitted=date(2026, 10, 1),
        first_reviewed=date(2026, 10, 3),
        decided=date(2026, 10, 10),
        outcome=DecisionOutcome.APPROVED,
        rounds=2,
        clock=clock,
    )

    summary = selectors.summary(viewer=lead, flt=window(clock), clock=clock)

    assert summary.time_to_first_review.median_hours == 48
    assert summary.time_to_first_review.imported_count == 1
    assert summary.rounds_per_item.mean == 2
    assert summary.throughput.imported_count == 1
    assert summary.time_per_round.count == 0
    assert summary.imported_from == date(2026, 10, 1)
    assert summary.imported_to == date(2026, 10, 10)


def test_imported_dates_not_the_import_time_decide_the_period(lead: User, clock: FixedClock) -> None:
    import_row("MCR-25-001", submitted=date(2025, 3, 1), first_reviewed=date(2025, 3, 2), clock=clock)

    summary = selectors.summary(viewer=lead, flt=window(clock), clock=clock)

    assert summary.time_to_first_review.count == 0


def test_include_legacy_false_drops_imported_rows(two_round_item: ReviewItem, lead: User, clock: FixedClock) -> None:
    import_row("MCR-26-002", submitted=date(2026, 10, 1), first_reviewed=date(2026, 10, 2), clock=clock)

    summary = selectors.summary(viewer=lead, flt=window(clock, include_legacy=False), clock=clock)

    assert summary.time_to_first_review.imported_count == 0
    assert summary.time_to_first_review.native_count == 1


def test_product_channel_and_partner_filters_narrow(two_round_item: ReviewItem, lead: User, clock: FixedClock) -> None:
    by_product = selectors.summary(viewer=lead, flt=window(clock, product=(Product.CREDIT_CARD,)), clock=clock)
    by_channel = selectors.summary(viewer=lead, flt=window(clock, channel=(Channel.LANDING_PAGE,)), clock=clock)
    by_partner = selectors.summary(viewer=lead, flt=window(clock, partner_id=(999,)), clock=clock)

    assert by_product.throughput.count == 0
    assert by_channel.throughput.count == 2
    assert by_partner.throughput.count == 0


def test_a_measurement_belongs_to_the_period_of_its_end(
    two_round_item: ReviewItem, lead: User, clock: FixedClock
) -> None:
    # The item was decided 3 days ago (T+8h) and 2 days ago (T+34h); a window ending 3 days ago has the first only.
    flt = MetricsFilter(period_from=clock.today() - timedelta(days=10), period_to=clock.today() - timedelta(days=3))

    summary = selectors.summary(viewer=lead, flt=flt, clock=clock)

    assert summary.throughput.count == 1
    assert summary.time_per_round.count == 1
    assert summary.rounds_per_item.count == 0


def test_fix_live_runs_from_reopen_to_confirmed_takedown(
    submit,
    reviewer: User,
    marketer: User,
    lead: User,
    clock: FixedClock,
) -> None:
    from metrics.tests.conftest import approve
    from reviews.decisions import pull_item
    from reviews.models import Placement
    from reviews.placements import PlacementInput, confirm_takedown, record_placement
    from reviews.rereview import send_back

    item_id = submit(title="Live page").item_id
    approve(item_id, reviewer, clock)
    record_placement(
        actor=marketer, item_id=item_id, data=PlacementInput(location="Site", first_run=clock.today()), clock=clock
    )
    clock.advance(timedelta(days=1))
    send_back(item_id=item_id, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)
    clock.advance(timedelta(hours=2))
    pull_item(actor=reviewer, item_id=item_id, reason="Rates outdated", clock=clock)

    open_now = selectors.summary(viewer=lead, flt=window(clock), clock=clock)
    clock.advance(timedelta(hours=4))
    confirm_takedown(actor=marketer, placement_id=Placement.objects.get(item_id=item_id).pk, clock=clock)
    fixed = selectors.summary(viewer=lead, flt=window(clock), clock=clock)

    assert (open_now.time_to_fix_live.count, open_now.open_fix_live.count) == (0, 1)
    # Pulled, takedown not yet confirmed: still open, but not a re-review in the queue (nit 10).
    assert (open_now.open_fix_live.in_rereview, open_now.open_fix_live.awaiting_takedown) == (0, 1)
    assert open_now.open_fix_live.oldest_hours == 2
    assert (fixed.time_to_fix_live.count, fixed.time_to_fix_live.median_hours) == (1, 6)
    assert fixed.open_fix_live.count == 0


def test_waiting_counts_equal_the_queue_views(submit, lead: User, clock: FixedClock) -> None:
    for days in (1, 4, 8, 20):
        clock.advance(timedelta(days=-days))
        submit(title=f"Waiting {days}d")
        clock.advance(timedelta(days=days))
    import_row("MCR-25-009", submitted=date(2025, 1, 2), clock=clock)  # an open tracker row: not in the queue

    summary = selectors.summary(viewer=lead, flt=window(clock), clock=clock)

    counts = {w.more_than_days: w.count for w in summary.waiting}
    assert counts == {3: 3, 7: 2, 14: 1, 30: 0}
    for days, n in counts.items():
        page = list_items(viewer=lead, filters=ItemFilter(waiting_more_than_days=days), clock=clock, limit=500)
        assert len(page.rows) == n


def test_waiting_follows_the_product_filter(submit, lead: User, clock: FixedClock) -> None:
    clock.advance(timedelta(days=-5))
    submit(title="Old PL")
    clock.advance(timedelta(days=5))

    summary = selectors.summary(viewer=lead, flt=window(clock, product=(Product.CREDIT_CARD,)), clock=clock)

    assert {w.more_than_days: w.count for w in summary.waiting}[3] == 0


@pytest.mark.parametrize("metric", list(MetricName))
def test_items_behind_a_number_are_exactly_that_many(
    metric: MetricName, two_round_item: ReviewItem, lead: User, clock: FixedClock
) -> None:
    import_row(
        "MCR-26-003",
        submitted=date(2026, 10, 1),
        first_reviewed=date(2026, 10, 3),
        decided=date(2026, 10, 9),
        outcome=DecisionOutcome.REJECTED,
        rounds=3,
        clock=clock,
    )
    flt = window(clock)
    summary = selectors.summary(viewer=lead, flt=flt, clock=clock)
    stat = {
        M.TIME_TO_FIRST_REVIEW: summary.time_to_first_review,
        M.TIME_PER_ROUND: summary.time_per_round,
        M.ROUNDS_PER_ITEM: summary.rounds_per_item,
        M.TIME_TO_FIX_LIVE: summary.time_to_fix_live,
        M.THROUGHPUT: summary.throughput,
    }[metric]

    behind = selectors.metric_items(viewer=lead, metric=metric, flt=flt, clock=clock)

    assert behind.total == stat.count
    assert len(behind.rows) == stat.count
    assert sum(1 for r in behind.rows if r.source is MetricSource.IMPORTED) == stat.imported_count


def test_item_rows_carry_the_item_and_sort_by_value(two_round_item: ReviewItem, lead: User, clock: FixedClock) -> None:
    behind = selectors.metric_items(viewer=lead, metric=M.TIME_PER_ROUND, flt=window(clock), clock=clock)

    assert [r.value for r in behind.rows] == [8, 4]
    assert behind.rows[0].item.key == two_round_item.key
    assert behind.rows[0].item.status == ItemStatus.APPROVED


def test_open_fix_live_items_list_the_open_clocks(
    submit,
    reviewer: User,
    marketer: User,
    lead: User,
    clock: FixedClock,
) -> None:
    from metrics.tests.conftest import approve
    from reviews.placements import PlacementInput, record_placement
    from reviews.rereview import send_back

    item_id = submit(title="Live page").item_id
    approve(item_id, reviewer, clock)
    record_placement(
        actor=marketer, item_id=item_id, data=PlacementInput(location="Site", first_run=clock.today()), clock=clock
    )
    send_back(item_id=item_id, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)
    clock.advance(timedelta(hours=30))

    behind = selectors.metric_items(
        viewer=lead, metric=M.TIME_TO_FIX_LIVE, flt=window(clock), clock=clock, open_only=True
    )

    assert [(r.item.id, r.value, r.end) for r in behind.rows] == [(item_id, 30, None)]


def test_series_buckets_by_week_with_empty_weeks(two_round_item: ReviewItem, lead: User, clock: FixedClock) -> None:
    flt = MetricsFilter(period_from=date(2026, 10, 1), period_to=clock.today())  # Thu Oct 1 .. Sat Oct 24

    result = selectors.series(viewer=lead, metric=M.THROUGHPUT, bucket=MetricBucket.WEEK, flt=flt, clock=clock)

    assert [p.period_start for p in result.points] == [
        date(2026, 9, 28),
        date(2026, 10, 5),
        date(2026, 10, 12),
        date(2026, 10, 19),
    ]
    assert [p.count for p in result.points] == [0, 0, 0, 2]
    assert result.points[-1].value == 2
    # The first bucket's drill-down range is clipped to the period.
    assert (result.points[0].from_date, result.points[0].to_date) == (date(2026, 10, 1), date(2026, 10, 4))
    assert result.points[-1].to_date == clock.today()


def test_series_value_is_the_median_for_durations(two_round_item: ReviewItem, lead: User, clock: FixedClock) -> None:
    result = selectors.series(
        viewer=lead, metric=M.TIME_PER_ROUND, bucket=MetricBucket.MONTH, flt=window(clock), clock=clock
    )

    october = next(p for p in result.points if p.period_start == date(2026, 10, 1))
    assert (october.count, october.value) == (2, 6)
    assert (october.native_value, october.imported_value) == (6, None)


def test_series_points_carry_each_source_value(two_round_item: ReviewItem, lead: User, clock: FixedClock) -> None:
    import_row("MCR-26-020", submitted=date(2026, 10, 5), first_reviewed=date(2026, 10, 9), clock=clock)
    flt = MetricsFilter(period_from=date(2026, 10, 1), period_to=clock.today())

    result = selectors.series(
        viewer=lead, metric=M.TIME_TO_FIRST_REVIEW, bucket=MetricBucket.MONTH, flt=flt, clock=clock
    )

    (october,) = result.points
    assert (october.native_value, october.imported_value, october.value) == (5, 96, 50.5)


def test_marketers_cannot_read_metrics(marketer: User, clock: FixedClock) -> None:
    with pytest.raises(NotPermitted):
        selectors.summary(viewer=marketer, flt=window(clock), clock=clock)


def test_reviewers_can(reviewer: User, clock: FixedClock) -> None:
    assert selectors.summary(viewer=reviewer, flt=window(clock), clock=clock).throughput.count == 0


def test_defaults_are_the_last_90_days(clock: FixedClock) -> None:
    flt = selectors.metrics_filter(clock=clock)

    assert (flt.period_from, flt.period_to) == (clock.today() - timedelta(days=89), clock.today())


def test_a_backwards_period_is_refused(clock: FixedClock) -> None:
    with pytest.raises(InvalidInput):
        selectors.metrics_filter(period_from=clock.today(), period_to=clock.today() - timedelta(days=1), clock=clock)
