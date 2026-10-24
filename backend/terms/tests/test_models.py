from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from pydantic import ValidationError

from accounts.models import User
from core.db import constraint_name
from core.domain import CreditCardTerms, PersonalLoanTerms, Product
from terms.models import OfferTerms

JAN = datetime(2026, 1, 1, tzinfo=UTC)
JUN = datetime(2026, 6, 1, tzinfo=UTC)
DEC = datetime(2026, 12, 1, tzinfo=UTC)

PL = PersonalLoanTerms(
    apr_min=Decimal("7.49"),
    apr_max=Decimal("35.99"),
    amount_min=Decimal(1000),
    amount_max=Decimal(50000),
    term_months=(24, 36, 60),
    origination_fee_min_pct=Decimal(0),
    origination_fee_max_pct=Decimal(8),
)
CC = CreditCardTerms(
    purchase_apr_min=Decimal("19.99"),
    purchase_apr_max=Decimal("29.99"),
    balance_transfer_fee_pct=Decimal(3),
    annual_fee=Decimal(0),
    issuing_bank="Sponsor Bank, N.A.",
)


def _terms(
    lead: User,
    values: PersonalLoanTerms | CreditCardTerms,
    version: int,
    lower: datetime | None,
    upper: datetime | None,
) -> OfferTerms:
    return OfferTerms.objects.create(
        product=values.product,
        version=version,
        effective_range=DateTimeTZRange(lower, upper, "[)"),
        values=values.model_dump(mode="json"),
        created_by=lead,
        created_at=JAN,
    )


@pytest.mark.django_db
def test_offer_terms_round_trip_typed_values(lead: User) -> None:
    terms = _terms(lead, PL, 1, JAN, None)
    terms.refresh_from_db()

    assert terms.typed_values == PL


@pytest.mark.django_db
def test_offer_terms_exclusion_rejects_overlap_same_product(lead: User) -> None:
    _terms(lead, PL, 1, JAN, None)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        _terms(lead, PL, 2, JUN, None)

    assert constraint_name(caught.value) == "terms_no_overlap"


@pytest.mark.django_db
def test_offer_terms_exclusion_allows_adjacent_ranges(lead: User) -> None:
    _terms(lead, PL, 1, JAN, JUN)
    _terms(lead, PL, 2, JUN, None)

    assert OfferTerms.objects.count() == 2


@pytest.mark.django_db
def test_offer_terms_exclusion_allows_other_product(lead: User) -> None:
    _terms(lead, PL, 1, JAN, None)
    _terms(lead, CC, 1, JAN, None)

    assert OfferTerms.objects.count() == 2


@pytest.mark.django_db
def test_offer_terms_values_validated_on_save(lead: User) -> None:
    with pytest.raises(ValidationError, match="apr_min must not exceed apr_max"):
        OfferTerms.objects.create(
            product=Product.PERSONAL_LOAN,
            version=1,
            effective_range=DateTimeTZRange(JAN, None, "[)"),
            values={**PL.model_dump(mode="json"), "apr_min": "40"},
            created_by=lead,
            created_at=JAN,
        )


@pytest.mark.django_db
def test_offer_terms_values_product_must_match_column(lead: User) -> None:
    # Bypass save()'s validation to reach the CHECK (rows are immutable, so only an INSERT can try it).
    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        OfferTerms.objects.bulk_create(
            [
                OfferTerms(
                    product=Product.CREDIT_CARD,
                    version=1,
                    effective_range=DateTimeTZRange(JAN, None, "[)"),
                    values=PL.model_dump(mode="json"),
                    created_by=lead,
                    created_at=JAN,
                )
            ]
        )

    assert constraint_name(caught.value) == "terms_values_product_matches"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE terms_offerterms SET values = jsonb_set(values, '{apr_min}', '\"5.00\"') WHERE id = %s",
        "UPDATE terms_offerterms SET effective_range = tstzrange('2025-01-01', NULL) WHERE id = %s",
        "UPDATE terms_offerterms SET note = 'edited' WHERE id = %s",
        "DELETE FROM terms_offerterms WHERE id = %s",
    ],
)
def test_offer_terms_are_immutable_once_written(lead: User, sql: str) -> None:
    # Decisions record the terms versions they quote; editing one would rewrite every past approval.
    terms = _terms(lead, PL, 1, JAN, None)

    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, [terms.pk])


@pytest.mark.django_db
def test_offer_terms_range_can_be_closed_once(lead: User) -> None:
    terms = _terms(lead, PL, 1, JAN, None)

    OfferTerms.objects.filter(pk=terms.pk).update(effective_range=DateTimeTZRange(JAN, JUN, "[)"))

    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        OfferTerms.objects.filter(pk=terms.pk).update(effective_range=DateTimeTZRange(JAN, DEC, "[)"))


@pytest.mark.django_db
def test_offer_terms_version_unique_per_product(lead: User) -> None:
    _terms(lead, PL, 1, JAN, JUN)

    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        _terms(lead, PL, 1, JUN, DEC)

    assert constraint_name(caught.value) == "terms_version_unique_per_product"


@pytest.mark.django_db
def test_offer_terms_range_must_have_a_start(lead: User) -> None:
    with pytest.raises(IntegrityError) as caught, transaction.atomic():
        _terms(lead, PL, 1, None, JUN)

    assert constraint_name(caught.value) == "terms_range_bounded_below"
