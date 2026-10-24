"""Fast-track approval of generated terms-change versions: one click, and bulk with per-item outcomes."""

import re
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import User
from checks.models import Finding
from core.clock import FixedClock
from core.domain import DecisionLane, ItemStatus, PersonalLoanTerms, ReopenReason, Role
from core.errors import Conflict, InvalidInput, NotPermitted
from reviews.assignment import assign_item
from reviews.models import Decision, ReviewItem
from reviews.records import get_item_detail, version_diff
from reviews.rereview import send_back
from reviews.services import SubmitItemResult
from terms.fanout import fan_out_item
from terms.fast_track import bulk_fast_track_approve, fast_track_approve
from terms.models import OfferTerms
from terms.tests.conftest import NEW_FLOOR, PL_VALUES, UNQUALIFIED, WORKED_EXAMPLE, approve, go_live, publish

type Submit = Callable[..., SubmitItemResult]

REASON = "Offer terms updated; numbers only."


def _reopened(
    submit: Submit, reviewer: User, marketer: User, lead: User, clock: FixedClock, text: str = WORKED_EXAMPLE
) -> ReviewItem:
    """Approved, live, then fanned out after the lead's publish (the test publishes first)."""
    item_id = submit(content_text=text).item_id
    approve(item_id, reviewer, clock)
    go_live(ReviewItem.objects.get(pk=item_id), marketer, clock)
    return ReviewItem.objects.get(pk=item_id)


def _fan_out_all(*items: ReviewItem, clock: FixedClock) -> None:
    for item in items:
        fan_out_item(item_id=item.pk, clock=clock)
        item.refresh_from_db()


@pytest.mark.django_db
def test_one_click_approves_the_generated_version(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _reopened(submit, reviewer, marketer, lead, clock)
    new_terms = publish(lead, clock)
    _fan_out_all(item, clock=clock)
    assert item.current_version is not None

    result = fast_track_approve(
        actor=reviewer, item_id=item.pk, version_n=item.current_version.n, reason=REASON, clock=clock
    )

    item.refresh_from_db()
    decision = Decision.objects.get(pk=result.decision_id)
    assert (result.status, result.version_n) == (ItemStatus.APPROVED, 2)
    assert (item.status, item.reopen_reason) == (ItemStatus.APPROVED, None)
    assert decision.lane == DecisionLane.FAST_TRACK
    assert decision.ai_review_carried_from is not None
    assert decision.ai_review_carried_from.n == 1
    assert list(decision.terms_versions.values_list("pk", flat=True)) == [new_terms]  # pyrefly: ignore[missing-attribute]


@pytest.mark.django_db
def test_diff_of_generated_vs_approved_touches_only_the_numbers(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _reopened(submit, reviewer, marketer, lead, clock)
    publish(lead, clock)
    _fan_out_all(item, clock=clock)

    diff = version_diff(item_id=item.pk, from_n=1, to_n=2)

    deleted = [s.text for s in diff.segments if s.op == "delete"]
    inserted = [s.text for s in diff.segments if s.op == "insert"]
    numbers = re.compile(r"[\s$%.\d]+")
    assert all(numbers.fullmatch(t) for t in deleted + inserted), (deleted, inserted)
    assert "".join(deleted).count("7.49") == 2
    assert "".join(inserted).count("12.99") == 2
    assert ("311" in "".join(deleted), "337" in "".join(inserted)) == (True, True)


@pytest.mark.django_db
def test_bulk_approves_clean_items_and_skips_the_rest(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    clean = _reopened(submit, reviewer, marketer, lead, clock)
    flagged = _reopened(submit, reviewer, marketer, lead, clock, text=UNQUALIFIED)
    normal = submit().item_id  # submitted, not a fast-track version
    publish(lead, clock)
    _fan_out_all(clean, flagged, clock=clock)
    assert flagged.open_findings_count == 1  # the qualifier warning quotes a rewritten number

    result = bulk_fast_track_approve(
        actor=lead,
        item_ids=[clean.pk, flagged.pk, normal, 999_999],
        reason=REASON,
        seen_versions={clean.pk: 2, flagged.pk: 2, normal: 1, 999_999: 1},
        clock=clock,
    )

    assert result.succeeded == (clean.pk,)
    skipped = {s.item_id: s.code for s in result.skipped}
    assert skipped == {
        flagged.pk: "open_findings_block_decision",
        normal: "invalid_transition",
        999_999: "not_found",
    }
    assert ReviewItem.objects.get(pk=flagged.pk).status == ItemStatus.NEEDS_REREVIEW
    assert Finding.objects.filter(version=flagged.current_version, state="open").count() == 1


@pytest.mark.django_db
def test_bulk_is_lead_only(
    pl_terms: OfferTerms,
    submit: Submit,
    marketer: User,
    reviewer: User,
    lead: User,
    clock: FixedClock,
    user_factory: Callable[..., User],
) -> None:
    """Bulk actions are a lead's (product-spec Roles). A reviewer fast-tracks one item at a time, at the version on
    screen; a lead's bulk covers every reviewer's items."""
    mine = _reopened(submit, reviewer, marketer, lead, clock)
    theirs = _reopened(submit, reviewer, marketer, lead, clock)
    publish(lead, clock)
    _fan_out_all(mine, theirs, clock=clock)
    other = user_factory(roles=[Role.REVIEWER])
    assign_item(actor=lead, item_id=theirs.pk, assignee_id=other.pk, clock=clock)

    for actor in (reviewer, marketer, user_factory(roles=[Role.ADMIN])):
        with pytest.raises(NotPermitted):
            bulk_fast_track_approve(
                actor=actor, item_ids=[mine.pk], reason=REASON, seen_versions={mine.pk: 2}, clock=clock
            )
    assert ReviewItem.objects.get(pk=mine.pk).status == ItemStatus.NEEDS_REREVIEW

    result = bulk_fast_track_approve(
        actor=lead, item_ids=[mine.pk, theirs.pk], reason=REASON, seen_versions={mine.pk: 2, theirs.pk: 2}, clock=clock
    )

    assert (result.succeeded, result.skipped) == ((mine.pk, theirs.pk), ())


@pytest.mark.django_db
def test_bulk_needs_the_seen_version_of_every_item(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    """Without the version the lead saw, an item would be approved at whatever is current, possibly a version a later
    terms change generated after the page loaded. So every item needs one, and nothing is approved otherwise."""
    seen = _reopened(submit, reviewer, marketer, lead, clock)
    unseen = _reopened(submit, reviewer, marketer, lead, clock)
    publish(lead, clock)
    _fan_out_all(seen, unseen, clock=clock)

    with pytest.raises(InvalidInput) as caught:
        bulk_fast_track_approve(
            actor=lead, item_ids=[seen.pk, unseen.pk], reason=REASON, seen_versions={seen.pk: 2}, clock=clock
        )

    assert caught.value.fields[0].loc == ("body", "seen_versions")
    assert f"CP-{unseen.pk}" in caught.value.message
    assert f"CP-{seen.pk}" not in caught.value.message
    assert set(ReviewItem.objects.filter(pk__in=[seen.pk, unseen.pk]).values_list("status", flat=True)) == {
        ItemStatus.NEEDS_REREVIEW
    }


@pytest.mark.django_db
def test_single_is_the_assignee_or_a_lead(
    pl_terms: OfferTerms,
    submit: Submit,
    marketer: User,
    reviewer: User,
    lead: User,
    clock: FixedClock,
    user_factory: Callable[..., User],
) -> None:
    item = _reopened(submit, reviewer, marketer, lead, clock)
    publish(lead, clock)
    _fan_out_all(item, clock=clock)
    other = user_factory(roles=[Role.REVIEWER])

    with pytest.raises(NotPermitted):
        fast_track_approve(actor=other, item_id=item.pk, version_n=2, reason=REASON, clock=clock)
    with pytest.raises(NotPermitted):
        fast_track_approve(actor=marketer, item_id=item.pk, version_n=2, reason=REASON, clock=clock)
    fast_track_approve(actor=lead, item_id=item.pk, version_n=2, reason=REASON, clock=clock)

    assert ReviewItem.objects.get(pk=item.pk).status == ItemStatus.APPROVED


@pytest.mark.django_db
def test_fast_track_api(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _reopened(submit, reviewer, marketer, lead, clock)
    second = _reopened(submit, reviewer, marketer, lead, clock)
    publish(lead, clock)
    _fan_out_all(item, second, clock=clock)
    client = Client()
    client.force_login(reviewer)

    bulk_refused = client.post(
        "/api/items/bulk/fast-track-approve",
        {"item_ids": [second.pk], "reason": REASON, "seen_versions": [{"item_id": second.pk, "version_n": 2}]},
        content_type="application/json",
    )
    stale = client.post(
        f"/api/items/{item.pk}/fast-track-approve", {"version_n": 1, "reason": REASON}, content_type="application/json"
    )
    unversioned = client.post(
        f"/api/items/{item.pk}/fast-track-approve", {"reason": REASON}, content_type="application/json"
    )
    single = client.post(
        f"/api/items/{item.pk}/fast-track-approve", {"version_n": 2, "reason": REASON}, content_type="application/json"
    )
    client.force_login(lead)
    bulk_without_seen = client.post(
        "/api/items/bulk/fast-track-approve",
        {"item_ids": [second.pk], "reason": REASON},
        content_type="application/json",
    )
    bulk_partly_seen = client.post(
        "/api/items/bulk/fast-track-approve",
        {"item_ids": [second.pk, item.pk], "reason": REASON, "seen_versions": [{"item_id": item.pk, "version_n": 2}]},
        content_type="application/json",
    )
    bulk = client.post(
        "/api/items/bulk/fast-track-approve",
        {"item_ids": [second.pk], "reason": REASON, "seen_versions": [{"item_id": second.pk, "version_n": 2}]},
        content_type="application/json",
    )

    assert bulk_refused.status_code == 403
    assert bulk_refused.json()["code"] == "not_permitted"
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_version"
    assert unversioned.status_code == 422  # the version on screen is required
    assert single.status_code == 201, single.content
    assert (single.json()["lane"], single.json()["version_n"], single.json()["ai_review_carried_from_n"]) == (
        "fast_track",
        2,
        1,
    )
    assert bulk_without_seen.status_code == 422
    assert bulk_partly_seen.status_code == 422
    assert bulk_partly_seen.json()["fields"][0]["loc"] == ["body", "seen_versions"]
    assert bulk.status_code == 200
    assert bulk.json() == {"succeeded": [second.pk], "skipped": []}


@pytest.mark.django_db
def test_single_refuses_when_a_newer_version_arrived_after_the_screen_loaded(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    """The reviewer opened v2 (12.99%); a second terms change generated v3 (9.99%) before they clicked. The click
    approves v2 or nothing: a 409 naming the newer version, and the item stays in re-review."""
    item = _reopened(submit, reviewer, marketer, lead, clock)
    publish(lead, clock)
    _fan_out_all(item, clock=clock)
    clock.advance(timedelta(minutes=5))
    publish(lead, clock, NEW_FLOOR.model_copy(update={"apr_min": Decimal("9.99")}))
    _fan_out_all(item, clock=clock)
    assert item.current_version is not None
    assert item.current_version.n == 3
    client = Client()
    client.force_login(reviewer)

    response = client.post(
        f"/api/items/{item.pk}/fast-track-approve", {"version_n": 2, "reason": REASON}, content_type="application/json"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "stale_version"
    assert "v3" in response.json()["message"]
    assert ReviewItem.objects.get(pk=item.pk).status == ItemStatus.NEEDS_REREVIEW
    assert not Decision.objects.filter(item_id=item.pk, lane=DecisionLane.FAST_TRACK).exists()


@pytest.mark.django_db
def test_bulk_skips_an_item_whose_version_changed_since_it_was_seen(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    """The reviewer saw v2 (12.99%); a second terms change regenerated v3 (9.99%) before the click. Approving v3 in
    their name would record a decision on copy they never saw."""
    item = _reopened(submit, reviewer, marketer, lead, clock)
    publish(lead, clock)
    _fan_out_all(item, clock=clock)
    clock.advance(timedelta(minutes=5))
    publish(lead, clock, NEW_FLOOR.model_copy(update={"apr_min": Decimal("9.99")}))
    _fan_out_all(item, clock=clock)

    result = bulk_fast_track_approve(
        actor=lead, item_ids=[item.pk], reason=REASON, seen_versions={item.pk: 2}, clock=clock
    )

    assert result.succeeded == ()
    assert [(s.item_id, s.code) for s in result.skipped] == [(item.pk, "stale_version")]
    assert ReviewItem.objects.get(pk=item.pk).status == ItemStatus.NEEDS_REREVIEW


@pytest.mark.django_db
def test_only_a_generated_version_can_be_fast_tracked(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _reopened(submit, reviewer, marketer, lead, clock)
    send_back(item_id=item.pk, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)  # no terms change: v1 current

    with pytest.raises(Conflict) as caught:
        fast_track_approve(actor=reviewer, item_id=item.pk, version_n=1, reason=REASON, clock=clock)

    assert caught.value.code == "conflict"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("values", "numbers_change"),
    [
        (NEW_FLOOR, True),  # the APR floor the copy quotes
        (PL_VALUES.model_copy(update={"origination_fee_max_pct": Decimal(6)}), False),  # a fee the copy doesn't quote
    ],
)
def test_item_detail_says_whether_the_generated_version_changes_any_number(
    values: PersonalLoanTerms,
    numbers_change: bool,
    pl_terms: OfferTerms,
    submit: Submit,
    marketer: User,
    reviewer: User,
    lead: User,
    clock: FixedClock,
) -> None:
    """A re-review whose numbers didn't change is a confirmation (orchestrator ruling): the item says so."""
    item = _reopened(submit, reviewer, marketer, lead, clock)
    assert get_item_detail(item_id=item.pk, clock=clock).numbers_change is None  # approved v1: nothing generated

    publish(lead, clock, values)
    _fan_out_all(item, clock=clock)

    detail = get_item_detail(item_id=item.pk, clock=clock)
    assert (detail.status, detail.current_version_n) == (ItemStatus.NEEDS_REREVIEW, 2)
    assert detail.numbers_change is numbers_change
