from decimal import Decimal

import pytest

from checks.engine import TermsRefDraft, run_code_checks
from checks.engine.extract import analyze
from core.domain import Product

from .conftest import cc_terms, make_ctx, pl_terms


def refs(text: str, product: Product = Product.PERSONAL_LOAN, **kw: object) -> list[tuple[str, str, Decimal]]:
    result = run_code_checks(make_ctx(text, product=product, **kw))  # type: ignore[arg-type]
    return [(r.field, text[r.span.start : r.span.end], r.quoted_value) for r in result.terms_refs]


def test_apr_range_maps_to_min_and_max() -> None:
    assert refs("Rates from 7.49%\u201335.99% APR.") == [
        ("apr_min", "7.49%", Decimal("7.49")),
        ("apr_max", "35.99%", Decimal("35.99")),
    ]


def test_apr_range_with_words_and_label_first() -> None:
    assert refs("APRs range from 7.49% to 35.99% based on creditworthiness.") == [
        ("apr_min", "7.49%", Decimal("7.49")),
        ("apr_max", "35.99%", Decimal("35.99")),
    ]


def test_as_low_as_maps_to_min_even_when_stale() -> None:
    assert refs("Rates as low as 6.99% APR.") == [("apr_min", "6.99%", Decimal("6.99"))]


def test_up_to_apr_maps_to_max() -> None:
    assert refs("APR up to 35.99%.") == [("apr_max", "35.99%", Decimal("35.99"))]


def test_unqualified_apr_maps_by_matching_current_terms() -> None:
    assert refs("Get 7.49% APR today.") == [("apr_min", "7.49%", Decimal("7.49"))]
    assert refs("Get 12.99% APR today.") == []


def test_amount_range_and_up_to() -> None:
    assert refs("Borrow $1,000 to $50,000.") == [
        ("amount_min", "$1,000", Decimal(1000)),
        ("amount_max", "$50,000", Decimal(50000)),
    ]
    assert refs("Loans up to $50,000 for whatever comes next.") == [("amount_max", "$50,000", Decimal(50000))]


def test_term_range_refs_the_numbers() -> None:
    assert refs("Repayment terms of 24 to 60 months.") == [
        ("term_months", "24", Decimal(24)),
        ("term_months", "60", Decimal(60)),
    ]


def test_origination_fee_range() -> None:
    assert refs("Origination fee of 0%\u20138% of the loan amount.") == [
        ("origination_fee_min_pct", "0%", Decimal(0)),
        ("origination_fee_max_pct", "8%", Decimal(8)),
    ]


def test_no_origination_fee_is_a_zero_claim_on_the_maximum() -> None:
    assert refs("No origination fees, ever.") == [("origination_fee_max_pct", "No origination fees", Decimal(0))]


def test_representative_example_yields_payment_ref_only() -> None:
    text = "Example: a $10,000 loan over 36 months at 12.99% APR has monthly payments of $337."
    assert refs(text) == [("example_payment", "$337", Decimal(337))]
    analysis = analyze(text, Product.PERSONAL_LOAN, pl_terms())
    (example,) = analysis.examples
    assert example.amount.value == Decimal(10000)
    assert example.term.months == 36
    assert example.apr.value == Decimal("12.99")


def test_example_apr_at_a_bound_is_also_a_ref() -> None:
    text = "Example: $10,000 for 36 months at 7.49% APR = $311/mo."
    assert refs(text) == [("apr_min", "7.49%", Decimal("7.49")), ("example_payment", "$311", Decimal(311))]


def test_card_intro_and_purchase_aprs() -> None:
    text = "0% intro APR for 15 months, then 19.99%\u201329.99% variable APR."
    assert refs(text, Product.CREDIT_CARD) == [
        ("intro_apr", "0%", Decimal(0)),
        ("intro_months", "15", Decimal(15)),
        ("purchase_apr_min", "19.99%", Decimal("19.99")),
        ("purchase_apr_max", "29.99%", Decimal("29.99")),
    ]


def test_card_fees() -> None:
    assert refs("No annual fee. 3% balance transfer fee.", Product.CREDIT_CARD) == [
        ("annual_fee", "No annual fee", Decimal(0)),
        ("balance_transfer_fee_pct", "3%", Decimal(3)),
    ]
    assert refs("$95 annual fee.", Product.CREDIT_CARD, terms=cc_terms(annual_fee=Decimal(95))) == [
        ("annual_fee", "$95", Decimal(95)),
    ]


def test_no_terms_means_no_refs() -> None:
    assert refs("Rates from 6.25% APR.", Product.MORTGAGE_PREQUAL) == []
    assert refs("Rates from 7.49%\u201335.99% APR.", terms=None) == []


def test_fee_percents_are_not_rates() -> None:
    analysis = analyze("3% balance transfer fee. Up to 5% cash back. 20% down.", Product.CREDIT_CARD, None)
    assert [p.kind for p in analysis.percents] == ["fee", "other", "down"]


def test_percent_labels() -> None:
    analysis = analyze("Interest rate 6.25% (6.41% APR).", Product.MORTGAGE_PREQUAL, None)
    first, second = analysis.percents
    assert (first.kind, first.apr_labeled) == ("rate", False)
    assert (second.kind, second.apr_labeled) == ("rate", True)


def test_curly_quotes_and_nbsp_do_not_shift_spans() -> None:
    text = "You\u2019ll love it.\u00a0Rates from 7.49%\u00a0APR \u2013 35.99%\u00a0APR."
    for field, quote, value in refs(text):
        assert field in {"apr_min", "apr_max"}
        assert Decimal(quote.rstrip("%")) == value


@pytest.mark.parametrize(
    ("text", "months"),
    [("60-month terms", 60), ("repay over 5 years", 60), ("36 monthly payments", 36), ("a 30-year mortgage", 360)],
)
def test_credit_terms_are_detected(text: str, months: int) -> None:
    (term,) = analyze(text, Product.PERSONAL_LOAN, None).terms
    assert term.months == months
    assert term.credit_context


@pytest.mark.parametrize(
    "text", ["Over 20 years of experience.", "Serving customers for 15 years.", "Funds in 2 days."]
)
def test_non_credit_durations_are_not_terms(text: str) -> None:
    assert not [t for t in analyze(text, Product.PERSONAL_LOAN, None).terms if t.credit_context]


def test_ref_types() -> None:
    result = run_code_checks(make_ctx("Rates from 7.49%\u201335.99% APR."))
    assert all(isinstance(r, TermsRefDraft) for r in result.terms_refs)
