"""The metric definitions (docs/plan/screens.md "Metrics"), as pure functions over event facts."""

from datetime import UTC, date, datetime, timedelta
from itertools import count

import pytest

from audit.payloads import LegacyTimeline
from core.domain import DecisionOutcome, EventType
from metrics.definitions import MetricBucket, MetricName, MetricSource
from metrics.measures import (
    Fact,
    Measurement,
    bucket_start,
    count_stat,
    duration_stat,
    imported_measurements,
    native_measurements,
    percentile,
)

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_ids = count(1)

E = EventType
Out = DecisionOutcome


def fact(
    event_type: EventType,
    hours: float,
    *,
    item_id: int = 1,
    entity_id: int | None = None,
    outcome: DecisionOutcome | None = None,
    placement_ids: tuple[int, ...] = (),
) -> Fact:
    return Fact(
        event_id=next(_ids),
        item_id=item_id,
        type=event_type,
        at=T0 + timedelta(hours=hours),
        entity_id=entity_id if entity_id is not None else item_id,
        outcome=outcome,
        placement_ids=placement_ids,
    )


def of(metric: MetricName, measurements: list[Measurement]) -> list[tuple[float, float]]:
    """(start offset hours, value) per measurement of one metric, in order."""
    return [((m.start - T0).total_seconds() / 3600, m.value) for m in measurements if m.metric is metric]


# A two-round item: submitted, claimed 5h later, changes requested at 8h; resubmitted at 30h, reviewed at 31h,
# approved at 34h.
TWO_ROUNDS = [
    fact(E.ITEM_SUBMITTED, 0),
    fact(E.ITEM_ASSIGNED, 0),
    fact(E.ITEM_REVIEW_STARTED, 5),
    fact(E.DECISION_RECORDED, 8, outcome=Out.CHANGES_REQUESTED),
    fact(E.ITEM_RESUBMITTED, 30),
    fact(E.ITEM_REVIEW_STARTED, 31),
    fact(E.DECISION_RECORDED, 34, outcome=Out.APPROVED),
]


def test_time_to_first_review_is_first_submission_to_first_review_started() -> None:
    measured, _ = native_measurements(TWO_ROUNDS)

    assert of(MetricName.TIME_TO_FIRST_REVIEW, measured) == [(0, 5)]


def test_each_round_runs_from_its_submission_to_its_decision() -> None:
    measured, _ = native_measurements(TWO_ROUNDS)

    assert of(MetricName.TIME_PER_ROUND, measured) == [(0, 8), (30, 4)]


def test_rounds_are_counted_at_the_terminal_decision() -> None:
    measured, _ = native_measurements(TWO_ROUNDS)

    rounds = [m for m in measured if m.metric is MetricName.ROUNDS_PER_ITEM]
    assert [(m.value, m.start, m.end) for m in rounds] == [(2, T0, T0 + timedelta(hours=34))]


def test_every_decision_counts_toward_throughput_with_its_outcome() -> None:
    measured, _ = native_measurements(TWO_ROUNDS)

    throughput = [m for m in measured if m.metric is MetricName.THROUGHPUT]
    assert [(m.outcome, m.end) for m in throughput] == [
        (Out.CHANGES_REQUESTED, T0 + timedelta(hours=8)),
        (Out.APPROVED, T0 + timedelta(hours=34)),
    ]
    assert all(m.source is MetricSource.NATIVE and m.value == 1 for m in throughput)


def test_a_fast_track_after_a_reopen_is_neither_a_round_nor_a_rounds_count() -> None:
    facts = [
        *TWO_ROUNDS,
        fact(E.ITEM_REOPENED, 100),
        fact(E.DECISION_RECORDED, 103, outcome=Out.APPROVED),
    ]

    measured, _ = native_measurements(facts)

    assert of(MetricName.TIME_PER_ROUND, measured) == [(0, 8), (30, 4)]
    assert [m.value for m in measured if m.metric is MetricName.ROUNDS_PER_ITEM] == [2]
    assert len([m for m in measured if m.metric is MetricName.THROUGHPUT]) == 3


def test_rounds_restart_after_a_new_round_from_withdrawn() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0),
        fact(E.DECISION_RECORDED, 2, outcome=Out.APPROVED),
        fact(E.ITEM_REOPENED, 50),
        fact(E.ITEM_WITHDRAWN, 51),
        fact(E.ITEM_NEW_ROUND_STARTED, 60),
        fact(E.DECISION_RECORDED, 62, outcome=Out.REJECTED),
    ]

    measured, _ = native_measurements(facts)

    assert [m.value for m in measured if m.metric is MetricName.ROUNDS_PER_ITEM] == [1, 1]
    assert of(MetricName.TIME_PER_ROUND, measured) == [(0, 2), (60, 2)]


def test_fix_live_stops_at_the_approval() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0),
        fact(E.DECISION_RECORDED, 1, outcome=Out.APPROVED),
        fact(E.ITEM_REOPENED, 10),
        fact(E.ITEM_REVIEW_STARTED, 12),
        fact(E.DECISION_RECORDED, 16, outcome=Out.APPROVED),
    ]

    measured, still_open = native_measurements(facts)

    assert of(MetricName.TIME_TO_FIX_LIVE, measured) == [(10, 6)]
    assert still_open == []


def test_fix_live_stops_when_every_requested_takedown_is_confirmed() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0),
        fact(E.DECISION_RECORDED, 1, outcome=Out.APPROVED),
        fact(E.ITEM_REOPENED, 10),
        fact(E.TAKEDOWN_REQUESTED, 11, entity_id=71),
        fact(E.TAKEDOWN_REQUESTED, 11, entity_id=72),
        fact(E.ITEM_WITHDRAWN, 11, placement_ids=(71, 72)),
        fact(E.TAKEDOWN_CONFIRMED, 13, entity_id=71),
        fact(E.TAKEDOWN_CONFIRMED, 20, entity_id=72),
        # A later round's approval is not the fix: the content came down at 20h.
        fact(E.ITEM_NEW_ROUND_STARTED, 30),
        fact(E.DECISION_RECORDED, 40, outcome=Out.APPROVED),
    ]

    measured, still_open = native_measurements(facts)

    assert of(MetricName.TIME_TO_FIX_LIVE, measured) == [(10, 10)]
    assert still_open == []


def test_fix_live_stays_open_until_the_last_takedown_is_confirmed() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0),
        fact(E.DECISION_RECORDED, 1, outcome=Out.APPROVED),
        fact(E.ITEM_REOPENED, 10),
        fact(E.TAKEDOWN_REQUESTED, 11, entity_id=71),
        fact(E.ITEM_WITHDRAWN, 11, placement_ids=(71, 72)),  # 72 was requested before (no new event)
        fact(E.TAKEDOWN_CONFIRMED, 13, entity_id=71),
    ]

    measured, still_open = native_measurements(facts)

    assert of(MetricName.TIME_TO_FIX_LIVE, measured) == []
    assert [(c.item_id, c.start) for c in still_open] == [(1, T0 + timedelta(hours=10))]


def test_a_reject_with_nothing_live_ends_the_fix_at_the_rejection() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0),
        fact(E.DECISION_RECORDED, 1, outcome=Out.APPROVED),
        fact(E.ITEM_REOPENED, 10),
        fact(E.ITEM_REVIEW_STARTED, 11),
        fact(E.DECISION_RECORDED, 15, outcome=Out.REJECTED),
    ]

    measured, still_open = native_measurements(facts)

    assert of(MetricName.TIME_TO_FIX_LIVE, measured) == [(10, 5)]
    assert still_open == []


def test_a_reject_waits_for_the_takedowns_it_requested() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0),
        fact(E.DECISION_RECORDED, 1, outcome=Out.APPROVED),
        fact(E.ITEM_REOPENED, 10),
        fact(E.DECISION_RECORDED, 15, outcome=Out.REJECTED),
        fact(E.TAKEDOWN_REQUESTED, 15, entity_id=9),  # written after the decision, same transaction
        fact(E.TAKEDOWN_CONFIRMED, 18, entity_id=9),
    ]

    measured, _ = native_measurements(facts)

    assert of(MetricName.TIME_TO_FIX_LIVE, measured) == [(10, 8)]


def test_request_changes_on_a_rereview_does_not_end_the_fix() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0),
        fact(E.DECISION_RECORDED, 1, outcome=Out.APPROVED),
        fact(E.ITEM_REOPENED, 10),
        fact(E.DECISION_RECORDED, 12, outcome=Out.CHANGES_REQUESTED),
        fact(E.ITEM_RESUBMITTED, 20),
        fact(E.DECISION_RECORDED, 22, outcome=Out.APPROVED_WITH_EDITS),
    ]

    measured, _ = native_measurements(facts)

    assert of(MetricName.TIME_TO_FIX_LIVE, measured) == [(10, 12)]


def test_items_are_measured_independently() -> None:
    facts = [
        fact(E.ITEM_SUBMITTED, 0, item_id=1),
        fact(E.ITEM_SUBMITTED, 1, item_id=2),
        fact(E.ITEM_REVIEW_STARTED, 2, item_id=2),
        fact(E.ITEM_REVIEW_STARTED, 4, item_id=1),
    ]

    measured, _ = native_measurements(sorted(facts, key=lambda f: (f.item_id, f.at, f.event_id)))

    assert sorted((m.item_id, m.value) for m in measured) == [(1, 4), (2, 1)]


def test_an_item_never_reviewed_has_no_first_review() -> None:
    measured, _ = native_measurements([fact(E.ITEM_SUBMITTED, 0)])

    assert measured == []


def _midnight(on: date) -> datetime:
    return datetime(on.year, on.month, on.day, tzinfo=UTC)


def test_imported_rows_contribute_first_review_rounds_and_the_final_decision() -> None:
    timeline = LegacyTimeline(
        submitted_at=_midnight(date(2026, 1, 5)),
        first_reviewed_at=_midnight(date(2026, 1, 7)),
        decided_at=_midnight(date(2026, 1, 20)),
        outcome=Out.APPROVED_WITH_EDITS,
        rounds=3,
    )

    measured = imported_measurements(item_id=9, timeline=timeline)

    assert {(m.metric, m.value) for m in measured} == {
        (MetricName.TIME_TO_FIRST_REVIEW, 48),
        (MetricName.ROUNDS_PER_ITEM, 3),
        (MetricName.THROUGHPUT, 1),
    }
    assert all(m.source is MetricSource.IMPORTED for m in measured)
    # The tracker has no per-round dates and no reopen: never a round time or a fix-live time.
    assert not {m.metric for m in measured} & {MetricName.TIME_PER_ROUND, MetricName.TIME_TO_FIX_LIVE}


def test_an_imported_open_row_contributes_only_what_it_has() -> None:
    timeline = LegacyTimeline(
        submitted_at=_midnight(date(2026, 1, 5)), first_reviewed_at=_midnight(date(2026, 1, 9)), rounds=2
    )

    measured = imported_measurements(item_id=9, timeline=timeline)

    assert [(m.metric, m.value) for m in measured] == [(MetricName.TIME_TO_FIRST_REVIEW, 96)]


def test_changes_requested_is_not_a_terminal_imported_outcome() -> None:
    timeline = LegacyTimeline(
        submitted_at=_midnight(date(2026, 1, 5)),
        decided_at=_midnight(date(2026, 1, 9)),
        outcome=Out.CHANGES_REQUESTED,
        rounds=1,
    )

    measured = imported_measurements(item_id=9, timeline=timeline)

    assert [m.metric for m in measured] == [MetricName.THROUGHPUT]


@pytest.mark.parametrize(
    ("values", "q", "expected"),
    [
        ([5.0], 0.9, 5.0),
        ([1.0, 2.0], 0.5, 1.5),
        ([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], 0.9, 9.1),  # Postgres percentile_cont
        ([3.0, 1.0, 2.0], 0.5, 2.0),
    ],
)
def test_percentile_interpolates_like_percentile_cont(values: list[float], q: float, expected: float) -> None:
    assert percentile(values, q) == pytest.approx(expected)


def _m(metric: MetricName, value: float, source: MetricSource = MetricSource.NATIVE) -> Measurement:
    return Measurement(metric=metric, item_id=1, source=source, start=T0, end=T0, value=value)


def test_duration_stat_splits_native_and_imported() -> None:
    ms = [
        _m(MetricName.TIME_TO_FIRST_REVIEW, 2),
        _m(MetricName.TIME_TO_FIRST_REVIEW, 4),
        _m(MetricName.TIME_TO_FIRST_REVIEW, 48, MetricSource.IMPORTED),
    ]

    stat = duration_stat(ms)

    assert (stat.count, stat.native_count, stat.imported_count, stat.median_hours) == (3, 2, 1, 4)


def test_empty_stats_have_no_value() -> None:
    assert duration_stat([]).median_hours is None
    assert count_stat([]).mean is None


def test_count_stat_mean_and_median() -> None:
    stat = count_stat([_m(MetricName.ROUNDS_PER_ITEM, v) for v in (1, 1, 4)])

    assert (stat.count, stat.mean, stat.median) == (3, 2, 1)


@pytest.mark.parametrize(
    ("on", "bucket", "expected"),
    [
        (date(2026, 10, 22), MetricBucket.WEEK, date(2026, 10, 19)),  # a Thursday -> its Monday
        (date(2026, 10, 19), MetricBucket.WEEK, date(2026, 10, 19)),
        (date(2026, 10, 22), MetricBucket.MONTH, date(2026, 10, 1)),
    ],
)
def test_bucket_start(on: date, bucket: MetricBucket, expected: date) -> None:
    assert bucket_start(on, bucket) == expected
