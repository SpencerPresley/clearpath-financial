"""The impact preview: what publishing proposed values now would do, without doing it."""

from collections.abc import Callable
from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from audit.models import Event
from checks.models import TermsRef
from core.clock import FixedClock
from core.domain import Channel, ItemStatus, Product, ReopenReason, TermsField
from core.errors import InvalidInput, NotPermitted
from reviews.models import ReviewItem, Version
from reviews.rereview import send_back
from reviews.services import SubmitItemResult
from reviews.tests.conftest import CC_VALUES, PL_VALUES
from reviews.tests.factories import make_partner
from terms.impact import FastTrackLane, impact_preview
from terms.models import OfferTerms
from terms.tests.conftest import NEW_FLOOR, WORKED_EXAMPLE, approve, go_live

type Submit = Callable[..., SubmitItemResult]


def _approved(submit: Submit, reviewer: User, clock: FixedClock, **fields: object) -> ReviewItem:
    item_id = submit(**{"content_text": WORKED_EXAMPLE, **fields}).item_id
    approve(item_id, reviewer, clock)
    return ReviewItem.objects.get(pk=item_id)


@pytest.fixture
def world(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, clock: FixedClock
) -> dict[str, ReviewItem]:
    partner = make_partner("LoanFinder")
    live = _approved(submit, reviewer, clock, channel=Channel.AFFILIATE_PAGE, partner_id=partner.pk)
    go_live(live, marketer, clock)
    idle = _approved(submit, reviewer, clock)
    stale = _approved(submit, reviewer, clock)
    go_live(stale, marketer, clock)
    TermsRef.objects.filter(version=stale.current_version, field="apr_max").update(quoted_value=Decimal("34.99"))
    rereview = _approved(submit, reviewer, clock)
    go_live(rereview, marketer, clock)
    send_back(item_id=rereview.pk, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)
    clean = _approved(submit, reviewer, clock, content_text="Personal loans from ClearPath. Apply online in minutes.")
    pending = ReviewItem.objects.get(pk=submit().item_id)  # submitted, not approved: never affected
    return {"live": live, "idle": idle, "stale": stale, "rereview": rereview, "clean": clean, "pending": pending}


@pytest.mark.django_db
def test_counts_split_and_lanes(
    world: dict[str, ReviewItem], pl_terms: OfferTerms, lead: User, clock: FixedClock
) -> None:
    preview = impact_preview(viewer=lead, product=Product.PERSONAL_LOAN, values=NEW_FLOOR, clock=clock)

    by_id = {i.item.id: i for i in preview.items}
    assert set(by_id) == {world["live"].pk, world["idle"].pk, world["stale"].pk, world["rereview"].pk}
    assert (preview.approved_items_quoting, preview.will_need_rereview, preview.will_expire) == (3, 2, 1)
    assert (preview.already_in_rereview, preview.normal_lane) == (1, 1)
    assert (preview.current_terms_id, preview.current_version, preview.next_version) == (pl_terms.pk, 1, 2)
    assert preview.changed_fields == (TermsField.APR_MIN,)
    assert preview.summary == (
        "3 approved items quote v1; 2 will need re-review, 1 will expire. "
        "1 item already in re-review will get the new numbers."
    )
    live = by_id[world["live"].pk]
    assert (live.is_live, live.will_become, live.lane, live.numbers_change) == (
        True,
        ItemStatus.NEEDS_REREVIEW,
        FastTrackLane.FAST_TRACK,
        True,
    )
    assert live.quoted_fields == (TermsField.APR_MIN, TermsField.EXAMPLE_PAYMENT, TermsField.APR_MAX)
    assert by_id[world["idle"].pk].will_become is ItemStatus.EXPIRED
    assert by_id[world["stale"].pk].lane is FastTrackLane.NORMAL
    assert by_id[world["rereview"].pk].will_become is ItemStatus.NEEDS_REREVIEW
    assert [(p.partner.name, p.item_count) for p in preview.partners] == [("LoanFinder", 1)]


@pytest.mark.django_db
def test_numbers_that_dont_change_are_flagged(world: dict[str, ReviewItem], lead: User, clock: FixedClock) -> None:
    raised_cap = PL_VALUES.model_copy(update={"amount_max": Decimal(60000)})  # nobody quotes the cap

    preview = impact_preview(viewer=lead, product=Product.PERSONAL_LOAN, values=raised_cap, clock=clock)

    assert preview.changed_fields == (TermsField.AMOUNT_MAX,)
    assert {i.numbers_change for i in preview.items if i.lane is FastTrackLane.FAST_TRACK} == {False}


@pytest.mark.django_db
def test_preview_writes_nothing(world: dict[str, ReviewItem], lead: User, clock: FixedClock) -> None:
    before = (Event.objects.count(), Version.objects.count(), OfferTerms.objects.count())

    impact_preview(viewer=lead, product=Product.PERSONAL_LOAN, values=NEW_FLOOR, clock=clock)

    assert (Event.objects.count(), Version.objects.count(), OfferTerms.objects.count()) == before
    assert ReviewItem.objects.get(pk=world["live"].pk).status == ItemStatus.APPROVED


@pytest.mark.django_db
def test_unchanged_values_and_empty_products(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    same = impact_preview(viewer=lead, product=Product.PERSONAL_LOAN, values=PL_VALUES, clock=clock)
    first_cc = impact_preview(viewer=lead, product=Product.CREDIT_CARD, values=CC_VALUES, clock=clock)

    assert (same.summary, same.items) == ("These are v1's values; nothing would change.", ())
    assert (first_cc.current_version, first_cc.next_version, first_cc.changed_fields) == (None, 1, ())
    assert first_cc.summary == "No approved items quote the current terms."


@pytest.mark.django_db
def test_lead_only_and_matching_product(pl_terms: OfferTerms, reviewer: User, lead: User, clock: FixedClock) -> None:
    with pytest.raises(NotPermitted):
        impact_preview(viewer=reviewer, product=Product.PERSONAL_LOAN, values=NEW_FLOOR, clock=clock)
    with pytest.raises(InvalidInput):
        impact_preview(viewer=lead, product=Product.CREDIT_CARD, values=NEW_FLOOR, clock=clock)


@pytest.mark.django_db
def test_query_count_does_not_grow_with_items(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    def measure() -> int:
        with CaptureQueriesContext(connection) as ctx:
            impact_preview(viewer=lead, product=Product.PERSONAL_LOAN, values=NEW_FLOOR, clock=clock)
        return len(ctx.captured_queries)

    names = iter(range(100))

    def grow(n: int) -> None:
        for _ in range(n):
            item = _approved(
                submit, reviewer, clock, partner_id=make_partner(f"P{next(names)}").pk, channel=Channel.AFFILIATE_PAGE
            )
            go_live(item, marketer, clock)

    grow(1)
    small = measure()
    grow(4)

    assert measure() == small


@pytest.mark.django_db
def test_preview_api(world: dict[str, ReviewItem], lead: User, reviewer: User) -> None:
    body = {"product": "personal_loan", "values": NEW_FLOOR.model_dump(mode="json")}
    client = Client()
    client.force_login(reviewer)
    refused = client.post("/api/terms/impact-preview", body, content_type="application/json")
    client.force_login(lead)
    response = client.post("/api/terms/impact-preview", body, content_type="application/json")

    assert refused.status_code == 403
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["will_need_rereview"] == 2
    assert {i["lane"] for i in data["items"]} == {"fast_track", "normal"}
    assert data["items"][0]["item"]["key"].startswith("CP-")
