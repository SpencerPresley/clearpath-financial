from datetime import date, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from checks.models import Finding
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import (
    Channel,
    DecisionLane,
    DecisionOutcome,
    FindingSource,
    ItemStatus,
    Market,
    Product,
    ReopenReason,
    RiskTier,
    Severity,
)
from core.errors import InvalidInput
from reviews.filters import ItemFilter, ItemSort
from reviews.models import APPROVED_OUTCOMES, Decision, Placement, ReviewItem
from reviews.selectors import filter_items, list_items, live_placements_q, queue_stats
from reviews.tests.factories import AT, make_item, make_partner, make_version


def _ids(page_rows: tuple[object, ...]) -> list[int]:
    return [row.id for row in page_rows]  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_filter_by_approval_date(marketer: User, reviewer: User, clock: FixedClock) -> None:
    # The board's "Approved (last 14 days)" column, which a saved view must express relative to today.
    now = clock.now()
    recent = make_item(marketer, status=ItemStatus.APPROVED, approved_at=now - timedelta(days=3))
    older = make_item(marketer, status=ItemStatus.APPROVED, approved_at=now - timedelta(days=20))
    make_item(marketer, status=ItemStatus.SUBMITTED)

    def ids(filters: ItemFilter) -> set[int]:
        return set(filter_items(viewer=reviewer, filters=filters, clock=clock).values_list("pk", flat=True))

    assert ids(ItemFilter(approved_within_days=14)) == {recent.pk}
    assert ids(ItemFilter(approved_after=now - timedelta(days=30), approved_before=now - timedelta(days=10))) == {
        older.pk
    }


@pytest.mark.django_db
def test_queue_sort_without_status_means_the_queue(marketer: User, reviewer: User, clock: FixedClock) -> None:
    queued = make_item(marketer, status=ItemStatus.SUBMITTED)
    make_item(marketer, status=ItemStatus.DRAFT)
    approved = make_item(marketer, status=ItemStatus.APPROVED)

    default = list_items(viewer=reviewer, filters=ItemFilter(), sort=ItemSort.QUEUE, clock=clock)
    explicit = list_items(
        viewer=reviewer, filters=ItemFilter(status=[ItemStatus.APPROVED]), sort=ItemSort.QUEUE, clock=clock
    )

    assert (_ids(default.rows), _ids(explicit.rows)) == ([queued.pk], [approved.pk])


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

    assert count_queries(3) == count_queries(30) == 2  # the page and its total


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
def test_every_stat_is_the_total_of_the_view_it_exports(
    marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock
) -> None:
    other = user_factory()
    old, recent = clock.now() - timedelta(days=5), clock.now() - timedelta(days=1)
    make_item(marketer, assignee=reviewer, submitted_at=recent)
    make_item(marketer, submitted_at=old)
    make_item(marketer, status=ItemStatus.IN_REVIEW, assignee=other, submitted_at=old)
    # A re-review a reviewer has opened is in review: counted in My queue, not Needs re-review.
    make_item(
        marketer,
        status=ItemStatus.IN_REVIEW,
        reopen_reason=ReopenReason.DRIFT_DETECTED,
        assignee=reviewer,
        submitted_at=recent,
    )
    make_item(marketer, status=ItemStatus.NEEDS_REREVIEW, reopen_reason=ReopenReason.TERMS_CHANGED, submitted_at=old)
    make_item(marketer, status=ItemStatus.CHANGES_REQUESTED, assignee=reviewer)
    make_item(marketer, status=ItemStatus.APPROVED)
    for n, status in enumerate((ItemStatus.SUBMITTED, ItemStatus.NEEDS_REREVIEW, ItemStatus.APPROVED)):
        make_item(
            None,
            status=status,
            reopen_reason=ReopenReason.TERMS_CHANGED if status is ItemStatus.NEEDS_REREVIEW else None,
            is_legacy=True,
            legacy_ref=f"REQ-{n}",
            markets=[],
            submitted_at=old,
            assignee=reviewer,
        )

    stats = queue_stats(viewer=reviewer, clock=clock)

    headline = {
        "open": stats.open,
        "mine": stats.mine,
        "unassigned": stats.unassigned,
        "needs_rereview": stats.needs_rereview,
        "waiting_over_3_days": stats.waiting_over_3_days,
    }
    assert headline == {"open": 5, "mine": 2, "unassigned": 2, "needs_rereview": 1, "waiting_over_3_days": 3}
    for sort in (ItemSort.QUEUE, ItemSort.TITLE):  # the set doesn't depend on the order it's shown in
        for name, count in headline.items():
            f = getattr(stats.filters, name)
            assert list_items(viewer=reviewer, filters=f, sort=sort, clock=clock).total == count, (name, sort)
        for s in stats.by_status:
            assert list_items(viewer=reviewer, filters=s.filters, sort=sort, clock=clock).total == s.count, s.status
    assert {s.status: s.count for s in stats.by_status}[ItemStatus.APPROVED] == 1  # legacy excluded


# --- column sorts ------------------------------------------------------------------------------------------------

ALL_STATUSES = ItemFilter(status=list(ItemStatus))


@pytest.fixture
def three_items(marketer: User, user_factory: UserFactory) -> tuple[ReviewItem, ReviewItem, ReviewItem]:
    """a, b, c: distinct on every sortable column, in a different order for each."""
    alex = user_factory(display_name="Alex Reviewer")
    bea = user_factory(display_name="Bea")
    User.objects.filter(pk=bea.pk).update(display_name="", email="bea@example.com")  # name falls back to email
    a = make_item(
        marketer,
        status=ItemStatus.APPROVED,
        risk_tier=RiskTier.LOW,
        assignee=alex,
        partner=make_partner("zeta lending"),
        open_findings_count=0,
        round=3,
    )
    b = make_item(marketer, status=ItemStatus.SUBMITTED, risk_tier=RiskTier.HIGH, open_findings_count=5, round=1)
    c = make_item(
        marketer,
        status=ItemStatus.NEEDS_REREVIEW,
        reopen_reason=ReopenReason.TERMS_CHANGED,
        risk_tier=RiskTier.MEDIUM,
        assignee=bea,
        partner=make_partner("Alpha Loans"),
        open_findings_count=2,
        round=2,
    )
    return a, b, c


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ascending", "descending", "expected"),
    [
        # Board order: submitted, in review, changes requested, needs re-review, approved, ...
        (ItemSort.STATUS, ItemSort.STATUS_DESC, "bca"),
        (ItemSort.RISK_TIER, ItemSort.RISK_TIER_DESC, "acb"),  # low, medium, high
        (ItemSort.ASSIGNEE, ItemSort.ASSIGNEE_DESC, "acb"),  # Alex, bea@…, unassigned last
        (ItemSort.PARTNER, ItemSort.PARTNER_DESC, "cab"),  # case-insensitive; no partner last
        (ItemSort.OPEN_FINDINGS, ItemSort.OPEN_FINDINGS_DESC, "acb"),
        (ItemSort.ROUND, ItemSort.ROUND_DESC, "bca"),
    ],
)
def test_column_sorts_run_both_ways(
    reviewer: User,
    clock: FixedClock,
    three_items: tuple[ReviewItem, ReviewItem, ReviewItem],
    ascending: ItemSort,
    descending: ItemSort,
    expected: str,
) -> None:
    by_letter: dict[str, int] = dict(zip("abc", (i.pk for i in three_items), strict=True))
    order = [by_letter[letter] for letter in expected]

    def ids(sort: ItemSort) -> list[int]:
        return _ids(list_items(viewer=reviewer, filters=ALL_STATUSES, sort=sort, clock=clock).rows)

    assert (ids(ascending), ids(descending)) == (order, order[::-1])


@pytest.mark.django_db
def test_title_sorts_both_ways(marketer: User, reviewer: User, clock: FixedClock) -> None:
    b = make_item(marketer, title="beta")
    a = make_item(marketer, title="Alpha")

    def ids(sort: ItemSort) -> list[int]:
        return _ids(list_items(viewer=reviewer, filters=ItemFilter(), sort=sort, clock=clock).rows)

    assert (ids(ItemSort.TITLE), ids(ItemSort.TITLE_DESC)) == ([a.pk, b.pk], [b.pk, a.pk])


@pytest.mark.django_db
@pytest.mark.parametrize("sort", list(ItemSort))
def test_keyset_pages_cross_ties_and_empty_relations(
    marketer: User, reviewer: User, user_factory: UserFactory, clock: FixedClock, sort: ItemSort
) -> None:
    # Tied keys, with and without an assignee and partner: a NULL in the row-value comparison would end the
    # walk at the first page boundary that lands on an unassigned item.
    other = user_factory(display_name="Same Name")
    partner = make_partner("Same partner")
    items = [
        make_item(
            marketer,
            title="Same title",
            assignee=other if n % 2 else None,
            partner=partner if n % 3 else None,
            submitted_at=AT,
            updated_at=AT,
        )
        for n in range(8)
    ]

    seen: list[int] = []
    cursor: str | None = None
    for _ in range(10):
        page = list_items(viewer=reviewer, filters=ItemFilter(), sort=sort, cursor=cursor, limit=3, clock=clock)
        seen.extend(_ids(page.rows))
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == _ids(list_items(viewer=reviewer, filters=ItemFilter(), sort=sort, limit=50, clock=clock).rows)
    assert sorted(seen) == sorted(i.pk for i in items)


# --- totals and row fields ---------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_page_carries_the_filtered_total(marketer: User, reviewer: User, clock: FixedClock) -> None:
    for _ in range(5):
        make_item(marketer, risk_tier=RiskTier.HIGH)
    make_item(marketer, risk_tier=RiskTier.LOW)
    high = ItemFilter(risk_tier=[RiskTier.HIGH])

    first = list_items(viewer=reviewer, filters=high, limit=2, clock=clock)
    second = list_items(viewer=reviewer, filters=high, cursor=first.next_cursor, limit=2, clock=clock)

    assert (first.total, second.total, len(second.rows)) == (5, 5, 2)


def _decide(item: ReviewItem, approver: User, outcome: DecisionOutcome, at: datetime, reason: str) -> Decision:
    return Decision.objects.create(
        item=item,
        version=item.current_version or make_version(item),
        outcome=outcome,
        lane=DecisionLane.STANDARD,
        approver=approver,
        reason=reason,
        ruleset_date=AT.date(),
        expires_at=AT + timedelta(days=180) if outcome in APPROVED_OUTCOMES else None,
        decided_at=at,
    )


@pytest.mark.django_db
def test_rows_carry_notes_latest_decision_and_approval_expiry(
    marketer: User, reviewer: User, clock: FixedClock
) -> None:
    expires = AT + timedelta(days=180)
    item = make_item(marketer, status=ItemStatus.APPROVED, notes="Check the APR footnote.", approval_expires_at=expires)
    make_version(item)
    _decide(item, reviewer, DecisionOutcome.CHANGES_REQUESTED, AT, "Add the APR range.")
    _decide(item, reviewer, DecisionOutcome.APPROVED, AT + timedelta(days=1), "Disclosures present.")
    undecided = make_item(marketer)

    rows = {r.id: r for r in list_items(viewer=reviewer, filters=ALL_STATUSES, clock=clock).rows}

    row = rows[item.pk]
    assert (row.notes, row.approval_expires_at) == ("Check the APR footnote.", expires)
    assert row.latest_decision is not None
    assert (row.latest_decision.outcome, row.latest_decision.reason, row.latest_decision.decided_at) == (
        DecisionOutcome.APPROVED,
        "Disclosures present.",
        AT + timedelta(days=1),
    )
    blank = rows[undecided.pk]
    assert (blank.notes, blank.approval_expires_at, blank.latest_decision) == ("", None, None)


@pytest.mark.django_db
def test_list_items_with_decisions_is_still_two_queries(marketer: User, reviewer: User, clock: FixedClock) -> None:
    def count_queries(n: int) -> int:
        partner = make_partner(f"Partner {n}")
        for _ in range(n):
            item = make_item(marketer, assignee=reviewer, partner=partner)
            make_version(item)
            _decide(item, reviewer, DecisionOutcome.CHANGES_REQUESTED, AT, "Fix it.")
        with CaptureQueriesContext(connection) as ctx:
            page = list_items(viewer=reviewer, filters=ItemFilter(), sort=ItemSort.ASSIGNEE, limit=100, clock=clock)
            assert all(row.latest_decision is not None for row in page.rows)
        return len(ctx.captured_queries)

    assert count_queries(3) == count_queries(30) == 2


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
