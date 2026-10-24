import pytest

from checks.engine import run_code_checks
from core.domain import Product

from .conftest import codes, make_ctx, quotes

MTG = Product.MORTGAGE_PREQUAL
COMPLIANT_PL = (
    "Personal loans from $1,000 to $50,000 with APRs from 7.49% to 35.99%, based on creditworthiness.\n\n"
    "Representative example: a $10,000 loan over 36 months at 12.99% APR has 36 monthly payments of $337."
)


@pytest.mark.parametrize(
    ("text", "trigger"),
    [
        ("Personal loans with 60-month terms.", "60"),
        ("Just $199/mo for the kitchen you want.", "$199"),
        ("Only $500 total cost of credit.", "$500"),
        ("Pay it off in 36 monthly payments.", "36"),
    ],
)
def test_trigger_terms_require_the_apr(text: str, trigger: str) -> None:
    result = run_code_checks(make_ctx(text))
    assert quotes(result, "closed_end.trigger_apr") == [trigger]


def test_trigger_term_alone_requires_full_repayment_terms() -> None:
    result = run_code_checks(make_ctx("Personal loans with 60-month terms at 12.99% APR."))
    assert "closed_end.trigger_apr" not in codes(result)
    assert quotes(result, "closed_end.trigger_repayment") == ["60"]


def test_payment_alone_requires_number_of_payments() -> None:
    result = run_code_checks(make_ctx("Payments as low as $199 a month at 12.99% APR."))
    assert quotes(result, "closed_end.trigger_repayment") == ["$199"]


@pytest.mark.parametrize(
    "text",
    [
        "No downpayment. No closing costs.",
        "Pay weekly if you like.",
        "Take years to repay.",
        "Rates from 7.49% APR.",
        "Over 20 years of experience helping families.",
        "Funds in as little as 1 business day.",
    ],
)
def test_commentary_non_triggers_do_not_flag(text: str) -> None:
    result = run_code_checks(make_ctx(text, terms=None))
    assert not {c for c in codes(result) if c.startswith("closed_end.trigger")}


def test_implied_down_payment_on_a_mortgage_needs_a_down_payment_statement() -> None:
    result = run_code_checks(make_ctx("Get 80 percent financing on your next home.", product=MTG))
    assert quotes(result, "closed_end.trigger_apr") == ["80 percent"]
    assert quotes(result, "closed_end.trigger_downpayment") == ["80 percent"]


def test_stated_down_payment_satisfies_the_down_payment_disclosure() -> None:
    text = "Buy with 10% down. 30-year loans, 360 monthly payments of $1,450 at 6.41% APR."
    assert "closed_end.trigger_downpayment" not in codes(run_code_checks(make_ctx(text, product=MTG)))


def test_variable_rate_needs_may_increase() -> None:
    result = run_code_checks(make_ctx("Variable-rate loans at 9.99% APR.", terms=None))
    assert quotes(result, "closed_end.rate_may_increase") == ["Variable-rate"]
    fixed = run_code_checks(make_ctx("Variable-rate loans at 9.99% APR. The rate may increase.", terms=None))
    assert "closed_end.rate_may_increase" not in codes(fixed)


def test_rate_not_labeled_apr_with_no_apr_anywhere() -> None:
    result = run_code_checks(make_ctx("Interest rate 8.5% on all loans.", terms=None))
    assert quotes(result, "closed_end.apr_label") == ["8.5%"]


def test_other_rate_alongside_apr_is_a_warning() -> None:
    result = run_code_checks(make_ctx("Interest rate 6.25% (6.41% APR).", product=MTG))
    assert quotes(result, "closed_end.other_rate") == ["6.25%"]
    assert "closed_end.apr_label" not in codes(result)


def test_fee_and_discount_percents_are_not_rates() -> None:
    text = "Origination fee up to 8%. Save 20% on interest with autopay. 95% of customers recommend us."
    result = run_code_checks(make_ctx(text, terms=None))
    assert "closed_end.apr_label" not in codes(result)


def test_example_must_be_labeled() -> None:
    text = "A $10,000 loan over 36 months at 12.99% APR has 36 monthly payments of $337."
    result = run_code_checks(make_ctx(text))
    assert quotes(result, "closed_end.example_labeled") == ["$337"]


def test_example_payment_must_match_its_terms() -> None:
    text = "Example: a $10,000 loan over 36 months at 12.99% APR has 36 monthly payments of $350."
    result = run_code_checks(make_ctx(text))
    (finding,) = [f for f in result.findings if f.rule_id == "closed_end.example_payment"]
    assert finding.quote == "$350"
    assert "$337" in finding.message


def test_compliant_personal_loan_copy_is_clean() -> None:
    result = run_code_checks(make_ctx(COMPLIANT_PL))
    assert not {c for c in codes(result) if c.startswith("closed_end.")}


def test_closed_end_rules_do_not_run_on_cards() -> None:
    result = run_code_checks(make_ctx("Just $25 a month.", product=Product.CREDIT_CARD))
    assert not {c for c in codes(result) if c.startswith("closed_end.")}
