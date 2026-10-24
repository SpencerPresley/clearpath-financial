from decimal import Decimal

from checks.engine import run_code_checks
from core.domain import Product, Severity

from .conftest import cc_terms, codes, make_ctx, quotes

CC = Product.CREDIT_CARD


def test_as_low_as_needs_range_and_qualifier() -> None:
    result = run_code_checks(make_ctx("Rates as low as 7.49% APR."))
    assert quotes(result, "pricing.as_low_as_range") == ["as low as 7.49%"]
    assert quotes(result, "pricing.creditworthiness_qualifier") == ["as low as 7.49%"]


def test_as_low_as_with_range_and_qualifier_is_clean() -> None:
    text = "Rates as low as 7.49% APR. APRs range from 7.49% to 35.99% based on creditworthiness."
    result = run_code_checks(make_ctx(text))
    assert not {c for c in codes(result) if c.startswith("pricing.")}


def test_subject_to_credit_approval_is_not_a_creditworthiness_qualifier() -> None:
    text = "Starting at 7.49% APR. APRs 7.49%\u201335.99%. Subject to credit approval."
    result = run_code_checks(make_ctx(text))
    assert codes(result) & {"pricing.as_low_as_range", "pricing.creditworthiness_qualifier"} == {
        "pricing.creditworthiness_qualifier"
    }


def test_rate_below_current_floor_is_bait_pricing() -> None:
    result = run_code_checks(make_ctx("Rates as low as 5.99% APR. APRs 5.99%\u201335.99% based on credit."))
    findings = [f for f in result.findings if f.rule_id == "pricing.terms_available"]
    assert [f.quote for f in findings] == ["5.99%", "5.99%"]
    assert findings[0].severity == Severity.BLOCKING
    assert "7.49%" in findings[0].message


def test_floor_within_range_but_stale_is_a_warning() -> None:
    result = run_code_checks(make_ctx("APRs 7.99%\u201335.99% based on creditworthiness."))
    assert quotes(result, "pricing.terms_current") == ["7.99%"]
    assert "pricing.terms_available" not in codes(result)


def test_amount_term_and_fee_claims_checked_against_terms() -> None:
    text = "Borrow up to $100,000. 72-month terms available. No origination fees."
    result = run_code_checks(make_ctx(text))
    assert quotes(result, "pricing.terms_available") == ["$100,000", "72", "No origination fees"]


def test_example_apr_and_term_must_be_offered() -> None:
    text = "Example: a $10,000 loan over 84 months at 4.99% APR has monthly payments of $139."
    assert quotes(run_code_checks(make_ctx(text)), "pricing.terms_available") == ["84", "4.99%"]


def test_card_fees_and_intro_checked_against_terms() -> None:
    text = "0% intro APR for 18 months, then 19.99%\u201329.99% variable APR. $0 annual fee. 5% balance transfer fee."
    result = run_code_checks(make_ctx(text, product=CC, terms=cc_terms(annual_fee=Decimal(95))))
    assert quotes(result, "pricing.terms_available") == ["18", "$0", "5%"]


def test_intro_offer_not_in_terms() -> None:
    text = "0% intro APR for 15 months, then 19.99%\u201329.99% variable APR."
    result = run_code_checks(make_ctx(text, product=CC, terms=cc_terms(intro_apr=None, intro_months=None)))
    assert quotes(result, "pricing.terms_available") == ["0%", "15"]


def test_values_matching_terms_are_clean() -> None:
    text = "0% intro APR for 15 months, then 19.99%\u201329.99% variable APR. $0 annual fee. 3% balance transfer fee."
    result = run_code_checks(make_ctx(text, product=CC))
    assert not {c for c in codes(result) if c.startswith("pricing.terms")}


def test_mortgage_has_no_terms_checks() -> None:
    result = run_code_checks(make_ctx("Rates from 2.99% APR.", product=Product.MORTGAGE_PREQUAL))
    assert not {c for c in codes(result) if c.startswith("pricing.terms")}
