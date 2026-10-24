"""The per-item fan-out after a terms change: generate v+1, then re-review (live) or expire (not live)."""

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import pytest

from accounts.models import User
from audit.models import Event
from checks.models import TermsRef
from core.clock import FixedClock
from core.domain import CheckStatus, EventType, ItemStatus, Product, ReopenReason, VersionOrigin
from reviews.models import ReviewItem, Version
from reviews.rereview import send_back
from reviews.services import SubmitItemResult
from reviews.tests.factories import make_item
from reviews.versions import start_new_round
from terms.fanout import FanOutOutcome, fan_out_item
from terms.models import OfferTerms
from terms.tests.conftest import NEW_FLOOR, WORKED_EXAMPLE, approve, go_live, publish

type Submit = Callable[..., SubmitItemResult]


def _approved(submit: Submit, reviewer: User, clock: FixedClock, text: str = WORKED_EXAMPLE) -> ReviewItem:
    item_id = submit(content_text=text).item_id
    approve(item_id, reviewer, clock)
    return ReviewItem.objects.get(pk=item_id)


def _fan_out(item: ReviewItem, lead: User, clock: FixedClock) -> FanOutOutcome:
    return fan_out_item(item_id=item.pk, clock=clock)


@pytest.mark.django_db
def test_worked_example_generates_v2_with_recomputed_payment(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _approved(submit, reviewer, clock)
    go_live(item, marketer, clock)
    new_terms_id = publish(lead, clock)

    outcome = _fan_out(item, lead, clock)

    item.refresh_from_db()
    v1, v2 = Version.objects.filter(item=item).order_by("n")
    assert outcome is FanOutOutcome.REOPENED_FAST_TRACK
    assert v2.content_text == WORKED_EXAMPLE.replace("7.49%", "12.99%").replace("$311", "$337")
    assert (v2.origin, v2.based_on, v2.author) == (VersionOrigin.FAST_TRACK, v1, lead)
    assert (item.status, item.reopen_reason, item.current_version) == (ItemStatus.NEEDS_REREVIEW, "terms_changed", v2)
    assert item.llm_check_status == CheckStatus.SKIPPED
    assert item.assignee == reviewer  # sticky: back to the approver
    assert item.open_findings_count == 0  # dismissals on v1 carried; nothing new
    assert set(TermsRef.objects.filter(version=v2).values_list("offer_terms_id", flat=True)) == {new_terms_id}
    reopened = Event.objects.get(type=EventType.ITEM_REOPENED, item_id=item.pk)
    assert reopened.payload == {
        "reason": "terms_changed",
        "offer_terms_id": new_terms_id,
        "generated_version_id": v2.pk,
    }
    assert reopened.actor == lead


@pytest.mark.django_db
def test_not_live_item_expires_and_new_round_offers_the_generated_version(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _approved(submit, reviewer, clock)
    publish(lead, clock)

    outcome = _fan_out(item, lead, clock)

    item.refresh_from_db()
    generated = item.current_version
    assert outcome is FanOutOutcome.EXPIRED
    assert (item.status, item.reopen_reason) == (ItemStatus.EXPIRED, "terms_changed")
    assert generated is not None
    assert generated.origin == VersionOrigin.FAST_TRACK
    expired = Event.objects.get(type=EventType.ITEM_EXPIRED, item_id=item.pk)
    assert expired.payload["generated_version_id"] == generated.pk

    result = start_new_round(actor=marketer, item_id=item.pk, clock=clock)

    v3 = Version.objects.get(pk=result.version_id)
    assert v3.content_text == generated.content_text
    assert "$337" in v3.content_text


@pytest.mark.django_db
def test_stale_terms_ref_goes_to_the_normal_lane(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _approved(submit, reviewer, clock)
    go_live(item, marketer, clock)
    # A ref whose text no longer reads as its quoted value: render_fast_track raises StaleTermsRef.
    TermsRef.objects.filter(version=item.current_version, field="apr_max").update(quoted_value=Decimal("34.99"))
    publish(lead, clock)

    outcome = _fan_out(item, lead, clock)

    item.refresh_from_db()
    assert outcome is FanOutOutcome.REOPENED_NORMAL_LANE
    assert Version.objects.filter(item=item).count() == 1
    assert (item.status, item.reopen_reason) == (ItemStatus.NEEDS_REREVIEW, "terms_changed")
    reopened = Event.objects.get(type=EventType.ITEM_REOPENED, item_id=item.pk)
    assert reopened.payload["generated_version_id"] is None


@pytest.mark.django_db
def test_fan_out_is_idempotent_under_redelivery(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _approved(submit, reviewer, clock)
    go_live(item, marketer, clock)
    publish(lead, clock)

    first = _fan_out(item, lead, clock)
    second = _fan_out(item, lead, clock)

    assert (first, second) == (FanOutOutcome.REOPENED_FAST_TRACK, FanOutOutcome.SKIPPED)
    assert Version.objects.filter(item=item).count() == 2
    assert Event.objects.filter(type=EventType.ITEM_REOPENED, item_id=item.pk).count() == 1


@pytest.mark.django_db
def test_item_no_longer_approved_is_skipped(
    pl_terms: OfferTerms, submit: Submit, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _approved(submit, reviewer, clock)
    publish(lead, clock)
    send_back(item_id=item.pk, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)  # the sweep got there first

    outcome = _fan_out(item, lead, clock)

    assert outcome is FanOutOutcome.SKIPPED
    assert Version.objects.filter(item=item).count() == 1


@pytest.mark.django_db
def test_approval_quoting_current_terms_is_skipped(
    pl_terms: OfferTerms, submit: Submit, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _approved(submit, reviewer, clock)

    assert _fan_out(item, lead, clock) is FanOutOutcome.SKIPPED
    assert ReviewItem.objects.get(pk=item.pk).status == ItemStatus.APPROVED


@pytest.mark.django_db
def test_legacy_items_are_skipped(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    legacy = make_item(None, status=ItemStatus.APPROVED, is_legacy=True, legacy_ref="REQ-7")
    publish(lead, clock)

    assert _fan_out(legacy, lead, clock) is FanOutOutcome.SKIPPED


@pytest.mark.django_db
def test_renders_with_the_terms_in_effect_when_it_runs(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    """v3 lands before v2's tasks drain: the item goes straight to v3's numbers, quoting v3."""
    from datetime import timedelta

    from terms.tests.conftest import NEW_FLOOR

    item = _approved(submit, reviewer, clock)
    go_live(item, marketer, clock)
    publish(lead, clock)
    clock.advance(timedelta(minutes=1))
    v3 = publish(lead, clock, NEW_FLOOR.model_copy(update={"apr_min": Decimal("9.99")}))

    _fan_out(item, lead, clock)

    item.refresh_from_db()
    assert item.current_version is not None
    assert "9.99% APR" in item.current_version.content_text
    assert set(TermsRef.objects.filter(version=item.current_version).values_list("offer_terms_id", flat=True)) == {v3}


@pytest.mark.django_db
def test_other_products_are_not_touched(
    pl_terms: OfferTerms, submit: Submit, reviewer: User, lead: User, clock: FixedClock
) -> None:
    from terms.selectors import affected_approvals

    item = _approved(submit, reviewer, clock)
    publish(lead, clock)

    assert [a.item_id for a in affected_approvals(product=Product.PERSONAL_LOAN, clock=clock)] == [item.pk]
    assert affected_approvals(product=Product.CREDIT_CARD, clock=clock) == ()


@pytest.mark.django_db
def test_item_already_in_rereview_gets_a_generated_version(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    """Live content re-reviewed for expiry when the terms change: it can't be reaffirmed on the old numbers, so it
    gets a generated version (status and reason unchanged) and the fast-track lane opens."""
    item = _approved(submit, reviewer, clock)
    go_live(item, marketer, clock)
    send_back(item_id=item.pk, reason=ReopenReason.APPROVAL_EXPIRED, clock=clock)
    publish(lead, clock)

    first = _fan_out(item, lead, clock)
    again = _fan_out(item, lead, clock)

    item.refresh_from_db()
    assert (first, again) == (FanOutOutcome.REGENERATED, FanOutOutcome.SKIPPED)
    assert (item.status, item.reopen_reason) == (ItemStatus.NEEDS_REREVIEW, "approval_expired")
    assert item.current_version is not None
    assert item.current_version.origin == VersionOrigin.FAST_TRACK
    assert "$337" in item.current_version.content_text


@pytest.mark.django_db
def test_second_terms_change_regenerates_from_the_approved_text(
    pl_terms: OfferTerms, submit: Submit, marketer: User, reviewer: User, lead: User, clock: FixedClock
) -> None:
    item = _approved(submit, reviewer, clock)
    go_live(item, marketer, clock)
    publish(lead, clock)
    _fan_out(item, lead, clock)
    clock.advance(timedelta(days=1))
    publish(lead, clock, NEW_FLOOR.model_copy(update={"apr_min": Decimal("9.99")}))

    outcome = _fan_out(item, lead, clock)

    v1, _v2, v3 = Version.objects.filter(item=item).order_by("n")
    assert outcome is FanOutOutcome.REGENERATED
    assert (v3.origin, v3.based_on) == (VersionOrigin.FAST_TRACK, v1)
    assert v3.content_text == WORKED_EXAMPLE.replace("7.49%", "9.99%").replace("$311", "$323")
    assert Event.objects.filter(type=EventType.ITEM_REOPENED, item_id=item.pk).count() == 1
