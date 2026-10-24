"""The thin layer: fetch-url, drift reads and Check now, the demo pages and their switch."""

from collections.abc import Iterator

import pytest
from django.core.cache import cache
from django.test import Client

from accounts.models import User
from conftest import UserFactory
from core.clock import FixedClock
from core.domain import DriftResult, DriftTrigger, Role
from drift import demo, intake, services
from drift.compare import compare
from drift.extract import visible_text
from drift.fetcher import FetchedPage, FetchError, FetchFailure
from drift.tests.conftest import page_with
from reviews.models import Placement, ReviewItem, Snapshot
from reviews.placements import PlacementInput, record_placement

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    cache.clear()  # demo switches and throttle counters
    yield
    cache.clear()


def signed_in(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


# --- fetch-url -------------------------------------------------------------------------------------------------


def fake_fetch(monkeypatch: pytest.MonkeyPatch, result: FetchedPage | FetchError) -> list[str]:
    urls: list[str] = []

    async def fetch(url: str) -> FetchedPage:
        urls.append(url)
        if isinstance(result, FetchError):
            raise result
        return result

    monkeypatch.setattr(intake, "fetch_page", fetch)
    return urls


def test_fetch_url_returns_visible_text_and_title(marketer: User, monkeypatch: pytest.MonkeyPatch) -> None:
    html = (
        "<html><head><title>PL offer</title><script>x=1</script></head><body><p>Rates from 7.49% APR.</p></body></html>"
    )
    urls = fake_fetch(
        monkeypatch,
        FetchedPage(
            url="https://partner.example/a",
            final_url="https://partner.example/b",
            status=200,
            content_type="text/html",
            text=html,
        ),
    )

    response = signed_in(marketer).post(
        "/api/items/fetch-url", {"url": "https://partner.example/a"}, content_type="application/json"
    )

    assert response.status_code == 200, response.content
    assert response.json() == {
        "url": "https://partner.example/b",
        "title": "PL offer",
        "content_text": "Rates from 7.49% APR.",
    }
    assert urls == ["https://partner.example/a"]


def test_fetch_url_refusals_are_422_on_the_url_field(marketer: User, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_fetch(monkeypatch, FetchError(FetchFailure.ADDRESS_NOT_ALLOWED))

    response = signed_in(marketer).post(
        "/api/items/fetch-url", {"url": "https://intranet.example/"}, content_type="application/json"
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_input"
    assert body["details"] == {"reason": "address_not_allowed"}
    assert body["fields"][0]["loc"] == ["body", "url"]
    assert "private or internal network" in body["message"]


def test_fetch_url_goes_through_the_real_guard(marketer: User) -> None:
    response = signed_in(marketer).post(
        "/api/items/fetch-url", {"url": "http://169.254.169.254/latest/meta-data/"}, content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["details"]["reason"] == "address_not_allowed"


def test_fetch_url_with_no_readable_text(marketer: User, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_fetch(
        monkeypatch,
        FetchedPage(
            url="https://spa.example/",
            final_url="https://spa.example/",
            status=200,
            content_type="text/html",
            text="<html><body><div id='root'></div><script src='app.js'></script></body></html>",
        ),
    )

    response = signed_in(marketer).post(
        "/api/items/fetch-url", {"url": "https://spa.example/"}, content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["details"]["reason"] == "no_text"
    assert "JavaScript" in response.json()["message"]


def test_fetch_url_validates_the_scheme_and_needs_a_session(marketer: User) -> None:
    bad = signed_in(marketer).post("/api/items/fetch-url", {"url": "ftp://x.example"}, content_type="application/json")
    anonymous = Client().post("/api/items/fetch-url", {"url": "https://x.example"}, content_type="application/json")

    assert (bad.status_code, bad.json()["code"]) == (422, "validation_error")
    assert anonymous.status_code == 401


def test_fetch_url_is_rate_limited_per_user(marketer: User, reviewer: User, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_fetch(monkeypatch, FetchError(FetchFailure.TIMEOUT))
    client = signed_in(marketer)

    codes = [
        client.post("/api/items/fetch-url", {"url": "https://x.example/"}, content_type="application/json").status_code
        for _ in range(21)
    ]
    other = signed_in(reviewer).post(
        "/api/items/fetch-url", {"url": "https://x.example/"}, content_type="application/json"
    )

    assert codes[:20] == [422] * 20
    assert codes[20] == 429
    assert other.status_code == 422


# --- drift -----------------------------------------------------------------------------------------------------


def test_item_drift_lists_placements_with_their_latest_check(
    placement: Placement, approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    record_placement(
        actor=marketer,
        item_id=approved.pk,
        data=PlacementInput(location="Print ad", first_run=clock.today()),
        clock=clock,
    )
    for copy in ("Old text entirely", None):  # an older check that found the copy missing, then the latest
        snapshot_id = services.request_check(
            actor=reviewer, placement_id=placement.pk, trigger=DriftTrigger.MANUAL, clock=clock
        )
        claim = services.claim(snapshot_id=snapshot_id, clock=clock)
        assert claim is not None
        services.complete(claim=claim, page=page_with(copy) if copy else page_with(), clock=clock)

    response = signed_in(reviewer).get(f"/api/items/{approved.pk}/drift")

    assert response.status_code == 200
    (row,) = response.json()["placements"]  # the print placement has no URL
    assert (row["placement_id"], row["monitored"], row["is_live"], row["demo_page"]) == (placement.pk, True, True, None)
    latest = row["latest"]
    assert (latest["status"], latest["result"], latest["compared_version_n"], latest["trigger"]) == (
        "succeeded",
        "unchanged",
        1,
        "manual",
    )
    assert latest["requested_by"]["id"] == reviewer.pk
    assert "text" not in latest


def test_item_drift_for_a_missing_item(reviewer: User) -> None:
    assert signed_in(reviewer).get("/api/items/999999/drift").status_code == 404


def test_check_now_queues_a_check(placement: Placement, reviewer: User, enqueued: list[int]) -> None:
    response = signed_in(reviewer).post(f"/api/placements/{placement.pk}/drift-checks")

    assert response.status_code == 202, response.content
    body = response.json()
    assert (body["status"], body["trigger"], body["placement_id"]) == ("pending", "manual", placement.pk)
    assert Snapshot.objects.get(pk=body["id"]).requested_by == reviewer


def test_check_now_refusals(
    placement: Placement,
    approved: ReviewItem,
    marketer: User,
    user_factory: UserFactory,
    clock: FixedClock,
    enqueued: list[int],
) -> None:
    stranger = user_factory(roles=[Role.MARKETER])
    no_url = record_placement(
        actor=marketer, item_id=approved.pk, data=PlacementInput(location="Print", first_run=clock.today()), clock=clock
    )

    assert signed_in(stranger).post(f"/api/placements/{placement.pk}/drift-checks").status_code == 403
    assert signed_in(marketer).post(f"/api/placements/{no_url}/drift-checks").status_code == 409
    assert signed_in(marketer).post("/api/placements/999999/drift-checks").status_code == 404
    assert Client().post(f"/api/placements/{placement.pk}/drift-checks").status_code == 401


def test_query_count_of_item_drift(
    placement: Placement,
    approved: ReviewItem,
    marketer: User,
    reviewer: User,
    clock: FixedClock,
    enqueued: list[int],
    django_assert_max_num_queries,
) -> None:
    for n in range(4):
        pid = record_placement(
            actor=marketer,
            item_id=approved.pk,
            data=PlacementInput(
                location=f"p{n}", url=f"https://p{n}.example/", first_run=clock.today(), monitored=True
            ),
            clock=clock,
        )
        services.request_check(actor=reviewer, placement_id=pid, trigger=DriftTrigger.MANUAL, clock=clock)
    client = signed_in(reviewer)

    with django_assert_max_num_queries(8):  # session + user + 4 reads, independent of placement count
        assert client.get(f"/api/items/{approved.pk}/drift").status_code == 200


# --- demo pages ------------------------------------------------------------------------------------------------


def test_demo_pages_are_public_and_show_the_original_copy() -> None:
    for page in demo.PAGES:
        response = Client().get(f"/demo-partners/{page.slug}/")
        assert response.status_code == 200
        text = visible_text(response.content.decode()).text
        assert "Demo partner page" in text
        assert compare(page.copy, text).result is DriftResult.UNCHANGED
        assert response["Cache-Control"].startswith("max-age=0")


def test_each_demo_edit_produces_its_expected_result(lead: User, settings) -> None:
    client = signed_in(lead)
    for page in demo.PAGES:
        assert (
            client.put(
                f"/api/demo/partner-pages/{page.slug}", {"edited": True}, content_type="application/json"
            ).status_code
            == 200
        )
        text = visible_text(Client().get(f"/demo-partners/{page.slug}/").content.decode()).text
        assert compare(page.copy, text).result == DriftResult(page.expected), page.slug


def test_demo_page_switch_is_lead_or_admin(reviewer: User, admin_user: User) -> None:
    assert (
        signed_in(reviewer)
        .put("/api/demo/partner-pages/lendcompare", {"edited": True}, content_type="application/json")
        .status_code
        == 403
    )
    response = signed_in(admin_user).put(
        "/api/demo/partner-pages/lendcompare", {"edited": True}, content_type="application/json"
    )
    assert response.json()["edited"] is True
    assert (
        signed_in(admin_user)
        .put("/api/demo/partner-pages/nope", {"edited": True}, content_type="application/json")
        .status_code
        == 404
    )

    listed = {p["slug"]: p for p in signed_in(reviewer).get("/api/demo/partner-pages").json()}
    assert listed["lendcompare"]["edited"] is True
    assert listed["cardscout"]["edited"] is False
    assert listed["lendcompare"]["url"].endswith("/demo-partners/lendcompare/")

    demo.reset_demo_pages()
    assert not demo.is_edited("lendcompare")


def test_unknown_demo_page_and_unsafe_methods() -> None:
    assert Client().get("/demo-partners/nope/").status_code == 404
    assert Client().post("/demo-partners/lendcompare/").status_code == 405


def test_drift_rows_point_at_demo_pages(
    approved: ReviewItem, marketer: User, reviewer: User, clock: FixedClock, enqueued: list[int]
) -> None:
    placement_id = demo.seed_placement(actor=marketer, item_id=approved.pk, slug="lendcompare", clock=clock)
    placement = Placement.objects.get(pk=placement_id)
    assert (placement.monitored, placement.last_run, placement.url) == (True, None, demo.page_url("lendcompare"))

    (row,) = signed_in(reviewer).get(f"/api/items/{approved.pk}/drift").json()["placements"]

    assert row["demo_page"]["slug"] == "lendcompare"
    assert row["demo_page"]["expected"] == "modified"
