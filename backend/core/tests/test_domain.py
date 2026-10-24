from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from core.domain import CreditCardTerms, OfferTermsValues, PersonalLoanTerms, Product

TERMS = TypeAdapter(OfferTermsValues)

PL = {
    "product": "personal_loan",
    "apr_min": "7.49",
    "apr_max": "35.99",
    "amount_min": "1000",
    "amount_max": "50000",
    "term_months": [24, 36, 60],
    "origination_fee_min_pct": "0",
    "origination_fee_max_pct": "8",
}


def test_terms_union_dispatches_on_product() -> None:
    terms = TERMS.validate_python(PL)

    assert isinstance(terms, PersonalLoanTerms)
    assert terms.apr_min == Decimal("7.49")


def test_personal_loan_rejects_inverted_apr_range() -> None:
    with pytest.raises(ValidationError, match="apr_min must not exceed apr_max"):
        TERMS.validate_python({**PL, "apr_min": "40"})


def test_credit_card_intro_fields_go_together() -> None:
    with pytest.raises(ValidationError, match="set together"):
        CreditCardTerms(
            purchase_apr_min=Decimal("19.99"),
            purchase_apr_max=Decimal("29.99"),
            intro_apr=Decimal(0),
            balance_transfer_fee_pct=Decimal(3),
            annual_fee=Decimal(0),
            issuing_bank="Sponsor Bank, N.A.",
        )


def test_terms_round_trip_through_json() -> None:
    terms = TERMS.validate_python(PL)

    assert TERMS.validate_json(TERMS.dump_json(terms)) == terms
    assert terms.product is Product.PERSONAL_LOAN
