"""Publishing a new offer-terms version."""

from decimal import Decimal

import pytest

from accounts.models import User
from audit.models import Event
from core.clock import FixedClock
from core.domain import EventType, Product
from core.errors import Conflict, InvalidInput, NotPermitted
from reviews.tests.conftest import CC_VALUES, PL_VALUES
from terms.models import OfferTerms
from terms.services import PublishTermsInput, publish_terms
from terms.tests.conftest import NEW_FLOOR, WORKED_EXAMPLE, approve, publish


@pytest.mark.django_db
def test_publish_closes_previous_and_opens_new(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    new_id = publish(lead, clock)

    pl_terms.refresh_from_db()
    new = OfferTerms.objects.get(pk=new_id)
    assert pl_terms.effective_range.upper == clock.now()  # pyrefly: ignore[missing-attribute]
    assert new.effective_range.lower == clock.now()  # pyrefly: ignore[missing-attribute]
    assert new.effective_range.upper is None  # pyrefly: ignore[missing-attribute]
    assert (new.version, new.typed_values, new.created_by) == (2, NEW_FLOOR, lead)
    event = Event.objects.get(type=EventType.TERMS_PUBLISHED)
    assert (event.entity, event.entity_id, event.actor) == ("offer_terms", new_id, lead)
    assert event.payload == {
        "offer_terms_id": new_id,
        "product": "personal_loan",
        "version": 2,
        "previous_offer_terms_id": pl_terms.pk,
        "affected_item_ids": [],
    }


@pytest.mark.django_db
def test_first_publish_has_no_previous(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    data = PublishTermsInput(product=Product.CREDIT_CARD, values=CC_VALUES, based_on_terms_id=None)
    new_id = publish_terms(actor=lead, data=data, clock=clock)

    new = OfferTerms.objects.get(pk=new_id)
    assert (new.product, new.version) == ("credit_card", 1)
    assert Event.objects.get(type=EventType.TERMS_PUBLISHED).payload["previous_offer_terms_id"] is None


@pytest.mark.django_db
def test_identical_values_refused(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    with pytest.raises(InvalidInput) as caught:
        publish(lead, clock, PL_VALUES)

    assert caught.value.fields[0].loc == ("body", "values")
    assert OfferTerms.objects.count() == 1


@pytest.mark.django_db
def test_values_must_match_product(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    data = PublishTermsInput(product=Product.CREDIT_CARD, values=PL_VALUES, based_on_terms_id=None)

    with pytest.raises(InvalidInput):
        publish_terms(actor=lead, data=data, clock=clock)


@pytest.mark.django_db
def test_only_leads_publish(pl_terms: OfferTerms, reviewer: User, admin_user: User, clock: FixedClock) -> None:
    for actor in (reviewer, admin_user):
        with pytest.raises(NotPermitted):
            publish(actor, clock)

    assert OfferTerms.objects.count() == 1


@pytest.mark.django_db
def test_affected_ids_recorded(
    pl_terms: OfferTerms, submit: object, reviewer: User, lead: User, clock: FixedClock
) -> None:
    quoting = submit(content_text=WORKED_EXAMPLE).item_id  # pyrefly: ignore[not-callable]
    approve(quoting, reviewer, clock)
    pending = submit(content_text=WORKED_EXAMPLE).item_id  # pyrefly: ignore[not-callable]  # not approved

    publish(lead, clock)

    payload = Event.objects.get(type=EventType.TERMS_PUBLISHED).payload
    assert payload["affected_item_ids"] == [quoting]
    assert pending not in payload["affected_item_ids"]


@pytest.mark.django_db
def test_versions_keep_counting(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    from datetime import timedelta

    publish(lead, clock)
    clock.advance(timedelta(days=1))
    third = publish(lead, clock, NEW_FLOOR.model_copy(update={"apr_max": Decimal("34.99")}))

    assert OfferTerms.objects.get(pk=third).version == 3
    assert OfferTerms.objects.filter(product="personal_loan", effective_range__upper_inf=True).count() == 1


@pytest.mark.django_db
def test_stale_base_is_refused_instead_of_reverting_another_leads_change(
    pl_terms: OfferTerms, lead: User, clock: FixedClock
) -> None:
    """Leads A and B both open the form at v1. A publishes a 12.99% floor (v2). B's fee change, built on v1's
    values, would put 7.49% back; it's refused so B re-runs the preview on v2."""
    publish(lead, clock)  # A
    b_values = PL_VALUES.model_copy(update={"origination_fee_max_pct": Decimal(7)})

    with pytest.raises(Conflict) as caught:
        publish_terms(
            actor=lead,
            data=PublishTermsInput(product=Product.PERSONAL_LOAN, values=b_values, based_on_terms_id=pl_terms.pk),
            clock=clock,
        )

    assert "v2 is in effect now" in caught.value.message
    assert OfferTerms.objects.filter(product="personal_loan").count() == 2
    assert Event.objects.filter(type=EventType.TERMS_PUBLISHED).count() == 1


@pytest.mark.django_db
def test_first_publish_must_say_there_was_no_base(pl_terms: OfferTerms, lead: User, clock: FixedClock) -> None:
    with pytest.raises(Conflict):
        publish_terms(
            actor=lead,
            data=PublishTermsInput(product=Product.CREDIT_CARD, values=CC_VALUES, based_on_terms_id=pl_terms.pk),
            clock=clock,
        )
