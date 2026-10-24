from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from checks.models import Finding
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import Channel, FindingSource, ItemStatus, Market, Product, ReopenReason, RiskTier, Severity
from core.errors import InvalidInput
from reviews.filters import ItemFilter, ItemSort
from reviews.models import Placement, ReviewItem
from reviews.selectors import filter_items, list_items, live_placements_q, queue_stats
from reviews.tests.factories import AT, make_item, make_partner, make_version


def _ids(page_rows: tuple[object, ...]) -> list[int]:
    return [row.id for row in page_rows]  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_queue_order_rereview_then_tier_then_age(marketer: User, reviewer: User, clock: FixedClock) -> None:
    old_low = make_item(marketer, risk_tier=RiskTier.LOW, submitted_at=AT - timedelta(days=5))
    new_high = make_item(marketer, risk_tier=RiskTier.HIGH, submitted_at=AT)
    old_high = make_item(marketer, risk_tier=RiskTier.HIGH, submitted_at=AT - timedelta(days=1))
    rereview = make_item(
        marketer,
        status=ItemStatus.NEEDS_REREVIEW,
        reopen_reason=ReopenReason.TERMS_CHANGED,
        risk_tier=RiskTier.LOW,
        submitted_at=AT,
    )

    page = list_items(viewer=reviewer, filters=ItemFilter(), clock=clock)

    assert _ids(page.rows) == [rereview.pk, old_high.pk, new_high.pk, old_low.pk]
    assert page.next_cursor is None


@pytest.mark.django_db
@pytest.mark.parametrize("sort", list(ItemSort))
def test_queue_keyset_pages_cover_all_rows_once(
    marketer: User, reviewer: User, clock: FixedClock, sort: ItemSort
) -> None:
    # Ties on every sort key except id, so the cursor's id tiebreak is what keeps pages disjoint.
    items = [make_item(marketer, title="Same title", submitted_at=AT, updated_at=AT) for _ in range(7)]
    items.append(make_item(marketer, title="Another", risk_tier=RiskTier.HIGH, submitted_at=AT + timedelta(hours=1)))

    seen: list[int] = []
    cursor: str | None = None
    for _ in range(10):
        page = list_items(viewer=reviewer, filters=ItemFilter(), sort=sort, cursor=cursor, limit=3, clock=clock)
        seen.extend(_ids(page.rows))
        cursor = page.next_cursor
        if cursor is None:
            break

    assert sorted(seen) == sorted(i.pk for i in items)
    assert len(seen) == len(set(seen))


@pytest.mark.django_db
def test_list_items_query_count_is_constant(marketer: User, reviewer: User, clock: FixedClock) -> None:
    def count_queries(n: int) -> int:
        partner = make_partner(f"Partner {n}")
        for _ in range(n):
            item = make_item(marketer, assignee=reviewer, partner=partner)
            make_version(item)
        with CaptureQueriesContext(connection) as ctx:
            page = list_items(viewer=reviewer, filters=ItemFilter(), limit=100, clock=clock)
            assert all(row.partner is not None for row in page.rows)
        return len(ctx.captured_queries)

    assert count_queries(3) == count_queries(30) == 1


@pytest.mark.django_db
def test_rows_carry_display_fields(marketer: User, reviewer: User, clock: FixedClock) -> None:
    partner = make_partner("LendStack")
    item = make_item(marketer, assignee=reviewer, partner=partner, tags=["promo"], open_findings_count=2)
    make_version(item)

    row = list_items(viewer=reviewer, filters=ItemFilter(), clock=clock).rows[0]

    assert row.key == f"CP-{item.pk}"
    assert row.partner is not None
    assert (row.partner.id, row.partner.name) == (partner.pk, "LendStack")
    assert row.owner is not None
    assert row.owner.name == "Morgan Marketer"
    assert row.assignee is not None
    assert row.assignee.name == "Riley Reviewer"
    assert (row.current_version_n, row.open_findings_count, row.tags) == (1, 2, ("promo",))
    assert row.age_days == 23  # AT is 2026-10-01 12:00, the clock 2026-10-24 15:00


@pytest.mark.django_db
def test_filter_mine_unassigned_and_waiting(
    marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    other = user_factory()
    mine = make_item(marketer, assignee=reviewer, submitted_at=clock.now() - timedelta(days=1))
    unassigned_old = make_item(marketer, submitted_at=clock.now() - timedelta(days=4))
    theirs = make_item(other, assignee=other, submitted_at=clock.now() - timedelta(days=10))

    def ids(f: ItemFilter, viewer: User = reviewer) -> set[int]:
        return set(filter_items(viewer=viewer, filters=f, clock=clock).values_list("pk", flat=True))

    assert ids(ItemFilter(mine=True)) == {mine.pk}
    assert ids(ItemFilter(unassigned=True)) == {unassigned_old.pk}
    assert ids(ItemFilter(waiting_more_than_days=3)) == {unassigned_old.pk, theirs.pk}
    assert ids(ItemFilter(submitted_by_me=True), viewer=marketer) == {mine.pk, unassigned_old.pk}


@pytest.mark.django_db
def test_filter_q_matches_title_case_insensitively_and_display_key(
    marketer: User, reviewer: User, clock: FixedClock
) -> None:
    spring = make_item(marketer, title="Spring Personal Loan email")
    other = make_item(marketer, title="Card landing page")

    def ids(q: str) -> set[int]:
        return set(filter_items(viewer=reviewer, filters=ItemFilter(q=q), clock=clock).values_list("pk", flat=True))

    assert ids("personal loan") == {spring.pk}
    assert ids(f"CP-{other.pk}") == {other.pk}
    assert ids("50%_off") == set()  # LIKE wildcards are literal


@pytest.mark.django_db
def test_filter_enums_tags_markets_and_findings(marketer: User, reviewer: User, clock: FixedClock) -> None:
    a = make_item(marketer, product=Product.CREDIT_CARD, channel=Channel.SMS, tags=["promo", "q4"], markets=[Market.CA])
    b = make_item(marketer, product=Product.PERSONAL_LOAN, tags=["promo"], open_findings_count=1)

    def ids(**kwargs: object) -> set[int]:
        f = ItemFilter(**kwargs)  # pyrefly: ignore[bad-argument-type]
        return set(filter_items(viewer=reviewer, filters=f, clock=clock).values_list("pk", flat=True))

    assert ids(product=[Product.CREDIT_CARD]) == {a.pk}
    assert ids(channel=[Channel.SMS, Channel.EMAIL]) == {a.pk, b.pk}
    assert ids(tag=["promo", "q4"]) == {a.pk}  # all of the given tags
    assert ids(market=[Market.CA]) == {a.pk}
    assert ids(has_open_findings=True) == {b.pk}
    assert ids(has_open_findings=False) == {a.pk}


@pytest.mark.django_db
def test_filter_run_dates_overlap_placements(marketer: User, reviewer: User, clock: FixedClock) -> None:
    ran_november = make_item(marketer, status=ItemStatus.APPROVED)
    ran_march = make_item(marketer, status=ItemStatus.APPROVED)
    for item, first, last in (
        (ran_november, date(2026, 11, 1), date(2026, 11, 30)),
        (ran_march, date(2026, 3, 1), None),
    ):
        Placement.objects.create(
            item=item,
            approved_version=make_version(item),
            location="site",
            first_run=first,
            last_run=last,
            created_by=marketer,
            created_at=AT,
        )

    f = ItemFilter(run_from=date(2026, 11, 15), run_to=date(2026, 12, 31))
    ids = set(filter_items(viewer=reviewer, filters=f, clock=clock).values_list("pk", flat=True))

    assert ids == {ran_november.pk, ran_march.pk}  # open-ended March placement still runs in November
    assert (
        set(
            filter_items(viewer=reviewer, filters=ItemFilter(run_to=date(2026, 2, 1)), clock=clock).values_list(
                "pk", flat=True
            )
        )
        == set()
    )


@pytest.mark.django_db
def test_live_placements_exclude_confirmed_takedowns_and_ended_runs(marketer: User, clock: FixedClock) -> None:
    item = make_item(marketer, status=ItemStatus.APPROVED)
    version = make_version(item)
    today = clock.today()

    def place(**kw: object) -> Placement:
        return Placement.objects.create(
            item=item, approved_version=version, location="x", created_by=marketer, created_at=AT, **kw
        )  # pyrefly: ignore[bad-argument-type]

    live = place(first_run=today - timedelta(days=3), last_run=None)
    place(first_run=today - timedelta(days=9), last_run=today - timedelta(days=1))
    place(first_run=today + timedelta(days=2), last_run=None)
    place(first_run=today - timedelta(days=3), takedown_state="confirmed", takedown_confirmed_at=AT)
    requested = place(first_run=today, takedown_state="requested", takedown_requested_at=AT)

    assert set(Placement.objects.filter(live_placements_q(today)).values_list("pk", flat=True)) == {
        live.pk,
        requested.pk,
    }


@pytest.mark.django_db
def test_bad_cursor_is_invalid_input(reviewer: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidInput):
        list_items(viewer=reviewer, filters=ItemFilter(), cursor="not-a-cursor", clock=clock)


@pytest.mark.django_db
def test_cursor_from_another_sort_is_invalid_input(marketer: User, reviewer: User, clock: FixedClock) -> None:
    for _ in range(3):
        make_item(marketer)
    cursor = list_items(viewer=reviewer, filters=ItemFilter(), sort=ItemSort.QUEUE, limit=1, clock=clock).next_cursor

    with pytest.raises(InvalidInput):
        list_items(viewer=reviewer, filters=ItemFilter(), sort=ItemSort.TITLE, cursor=cursor, clock=clock)


@pytest.mark.django_db
def test_queue_stats(marketer: User, reviewer: User, clock: FixedClock) -> None:
    make_item(marketer, assignee=reviewer)
    make_item(marketer, submitted_at=clock.now() - timedelta(days=4))
    make_item(marketer, status=ItemStatus.NEEDS_REREVIEW, reopen_reason=ReopenReason.TERMS_CHANGED, assignee=reviewer)
    make_item(marketer, status=ItemStatus.APPROVED)
    make_item(None, status=ItemStatus.APPROVED, is_legacy=True, legacy_ref="REQ-1", markets=[])
    ReviewItem.objects.update(submitted_at=clock.now() - timedelta(days=4))

    stats = queue_stats(viewer=reviewer, clock=clock)

    assert (stats.open, stats.mine, stats.unassigned, stats.needs_rereview, stats.waiting_over_3_days) == (
        3,
        2,
        1,
        1,
        3,
    )
    assert {s.status: s.count for s in stats.by_status}[ItemStatus.APPROVED] == 1  # legacy excluded


@pytest.mark.django_db
def test_findings_count_column_is_what_filters_use(marketer: User, reviewer: User, clock: FixedClock) -> None:
    # open_findings_count is denormalized; filters read the column, not a join over findings.
    item = make_item(marketer)
    version = make_version(item)
    Finding.objects.create(
        version=version,
        rule_id="r",
        citation="c",
        source=FindingSource.CODE,
        severity=Severity.WARNING,
        span_start=0,
        span_end=5,
        quote="Rates",
        message="m",
        created_at=AT,
    )

    ids = set(
        filter_items(viewer=reviewer, filters=ItemFilter(has_open_findings=True), clock=clock).values_list(
            "pk", flat=True
        )
    )

    assert ids == set()
