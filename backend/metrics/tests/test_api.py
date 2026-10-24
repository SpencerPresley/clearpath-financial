"""The metrics endpoints: thin over the selectors; permissions, query parsing, and a flat query count."""

from datetime import date, timedelta

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from core.clock import FixedClock
from core.domain import DecisionOutcome
from metrics.tests.conftest import import_row

pytestmark = pytest.mark.django_db

PATHS = [
    "/api/metrics/summary",
    "/api/metrics/series?metric=throughput",
    "/api/metrics/items?metric=time_to_first_review",
]


def client_for(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.parametrize("path", PATHS)
def test_marketers_get_403(marketer: User, path: str) -> None:
    response = client_for(marketer).get(path)

    assert response.status_code == 403
    assert response.json()["code"] == "not_permitted"


@pytest.mark.parametrize("path", PATHS)
def test_leads_get_200(lead: User, path: str) -> None:
    assert client_for(lead).get(path).status_code == 200


def test_summary_reads_list_filters_and_the_period(lead: User, clock: FixedClock) -> None:
    import_row(
        "MCR-26-010",
        submitted=date(2026, 3, 2),
        first_reviewed=date(2026, 3, 4),
        decided=date(2026, 3, 9),
        outcome=DecisionOutcome.APPROVED,
        clock=clock,
    )

    hit = client_for(lead).get(
        "/api/metrics/summary?period_from=2026-03-01&period_to=2026-03-31&product=personal_loan&product=credit_card"
    )
    miss = client_for(lead).get("/api/metrics/summary?period_from=2026-03-01&period_to=2026-03-31&product=credit_card")
    no_legacy = client_for(lead).get(
        "/api/metrics/summary?period_from=2026-03-01&period_to=2026-03-31&include_legacy=false"
    )

    body = hit.json()
    assert body["time_to_first_review"] == {
        "count": 1,
        "median_hours": 48.0,
        "p90_hours": 48.0,
        "native_count": 0,
        "imported_count": 1,
    }
    assert [w["more_than_days"] for w in body["waiting"]] == [3, 7, 14, 30]
    assert miss.json()["throughput"]["count"] == 0
    assert no_legacy.json()["throughput"]["count"] == 0


def test_backwards_period_is_a_422_on_period_from(lead: User) -> None:
    response = client_for(lead).get("/api/metrics/summary?period_from=2026-03-02&period_to=2026-03-01")

    assert response.status_code == 422
    assert response.json()["fields"][0]["loc"][-1] == "period_from"


def test_items_lists_imported_rows_with_their_ref(lead: User, clock: FixedClock) -> None:
    import_row("MCR-26-011", submitted=date(2026, 10, 1), first_reviewed=date(2026, 10, 2), clock=clock)

    rows = client_for(lead).get("/api/metrics/items?metric=time_to_first_review&period_from=2026-10-01").json()["rows"]

    assert [(r["source"], r["item"]["legacy_ref"], r["value"], r["item"]["is_legacy"]) for r in rows] == [
        ("imported", "MCR-26-011", 24.0, True)
    ]


def _grow(k: int, *, submit, reviewer: User, clock: FixedClock, serial: list[int]) -> None:
    from reviews.assignment import claim_item
    from reviews.decisions import DecisionInput, record_decision

    for _ in range(k):
        serial[0] += 1
        n = serial[0]
        item_id = submit(title=f"Grow {n}").item_id
        clock.advance(timedelta(hours=1))
        claim_item(actor=reviewer, item_id=item_id, clock=clock)
        record_decision(
            actor=reviewer,
            item_id=item_id,
            data=DecisionInput(outcome=DecisionOutcome.CHANGES_REQUESTED, version_n=1, reason="Fix it"),
            clock=clock,
        )
        import_row(
            f"MCR-26-{n:03d}",
            submitted=clock.today() - timedelta(days=5),
            first_reviewed=clock.today() - timedelta(days=4),
            decided=clock.today() - timedelta(days=2),
            outcome=DecisionOutcome.APPROVED,
            clock=clock,
        )


@pytest.mark.parametrize(
    "path",
    [
        "/api/metrics/summary",
        "/api/metrics/series?metric=time_per_round&bucket=week",
        "/api/metrics/items?metric=throughput",
        "/api/metrics/items?metric=time_to_fix_live&open_only=true",
    ],
)
def test_query_count_does_not_grow_with_the_data(
    path: str,
    submit,
    reviewer: User,
    lead: User,
    clock: FixedClock,
) -> None:
    client = client_for(lead)
    serial = [100]

    def measure() -> int:
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(path).status_code == 200
        return len(ctx.captured_queries)

    _grow(2, submit=submit, reviewer=reviewer, clock=clock, serial=serial)
    small = measure()
    _grow(6, submit=submit, reviewer=reviewer, clock=clock, serial=serial)
    large = measure()

    assert large == small
