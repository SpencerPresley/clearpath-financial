"""Suggested fixes come from the current offer terms or the copy itself, never from literals in the rules
(walkthrough B2: "as low as" suggested 7.49% while the terms floor was 9.99%, and the next finding said 7.49% isn't
offered). The shared fixtures use 7.49% / 19.99%-29.99%, the same values the old literals had, so every test here
runs with terms nobody would type by accident."""

import re
from dataclasses import replace
from decimal import Decimal

import pytest

from checks.engine import RULES, FindingDraft, run_code_checks
from checks.engine.config import DEFAULT_CONFIG
from core.domain import Channel, CreditCardTerms, PersonalLoanTerms, Product

from .conftest import cc_terms, make_ctx, pl_terms
from .samples import SAMPLES, Sample
from .test_samples import context

PL = pl_terms(apr_min=Decimal("11.11"), apr_max=Decimal("33.33"), amount_max=Decimal(44000))
CC = cc_terms(
    purchase_apr_min=Decimal("21.21"),
    purchase_apr_max=Decimal("28.28"),
    intro_apr=Decimal("1.99"),
    intro_months=9,
    balance_transfer_fee_pct=Decimal(4),
    annual_fee=Decimal(95),
    issuing_bank="Harborview Bank, N.A.",
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# Suggestions computed from the copy's own amount, term and APR (payment math), not quoted from anywhere.
_COMPUTED = frozenset({"closed_end.example_payment", "closed_end.trigger_repayment"})


def _numbers(text: str) -> set[Decimal]:
    return {Decimal(n) for n in _NUMBER.findall(text.replace(",", ""))}


def _terms_numbers(terms: PersonalLoanTerms | CreditCardTerms) -> set[Decimal]:
    return _numbers(" ".join(str(v) for v in terms.model_dump().values()))


def _with_odd_terms(sample: Sample) -> list[FindingDraft]:
    ctx = context(sample)
    odd = {Product.PERSONAL_LOAN: PL, Product.CREDIT_CARD: CC}.get(sample.product)
    return list(run_code_checks(replace(ctx, terms=odd)).findings)


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.name)
def test_every_number_in_a_suggestion_is_in_the_copy_or_the_terms(sample: Sample) -> None:
    odd = {Product.PERSONAL_LOAN: PL, Product.CREDIT_CARD: CC}.get(sample.product)
    company = _numbers(DEFAULT_CONFIG.postal_address)  # a configured company fact, not a rule literal
    allowed = _numbers(sample.text) | company | (_terms_numbers(odd) if odd is not None else set())
    for f in _with_odd_terms(sample):
        if f.suggested_fix is None or f.rule_id in _COMPUTED:
            continue
        invented = _numbers(f.suggested_fix) - allowed
        assert not invented, (f.rule_id, f.suggested_fix)


def _fix(text: str, rule_id: str, **kwargs: object) -> str | None:
    assert rule_id in RULES
    [finding] = [f for f in run_code_checks(make_ctx(text, **kwargs)).findings if f.rule_id == rule_id]  # pyrefly: ignore[bad-argument-type]
    return finding.suggested_fix


def test_as_low_as_suggests_the_current_range() -> None:
    assert _fix("Rates as low as 11.11% APR.", "pricing.as_low_as_range", terms=PL) == '"APRs from 11.11% to 33.33%"'
    cc = _fix("Purchase APRs as low as 21.21%.", "pricing.as_low_as_range", product=Product.CREDIT_CARD, terms=CC)
    assert cc == '"APRs from 21.21% to 28.28%"'


def test_as_low_as_without_terms_suggests_no_numbers() -> None:
    text = "Mortgage rates as low as 5.5% APR. Get prequalified."
    assert _fix(text, "pricing.as_low_as_range", product=Product.MORTGAGE_PREQUAL, terms=None) is None


def test_card_trigger_suggestions_use_the_card_terms() -> None:
    card = {"product": Product.CREDIT_CARD, "terms": CC}
    assert _fix("No annual fee.", "card.trigger_apr", **card) == '"21.21%\u201328.28% variable APR"'
    assert _fix("1% foreign transaction fee.", "card.trigger_annual_fee", **card) == '"$95 annual fee"'
    text = "Transfer your balance today. 21.21%\u201328.28% variable APR. $95 annual fee."
    assert _fix(text, "card.trigger_transaction_fees", **card) == '"4% balance transfer fee"'


def test_intro_suggestions_use_the_intro_terms_and_the_copys_rate() -> None:
    card = {"product": Product.CREDIT_CARD, "terms": CC}
    text = "Pay 1.99% APR for 9 months on purchases. $95 annual fee."
    assert _fix(text, "card.intro_label", **card) == '"1.99% intro APR"'
    intro = "1.99% intro APR on purchases. $95 annual fee."
    findings = [f for f in run_code_checks(make_ctx(intro, **card)).findings if f.rule_id == "card.intro_terms"]  # pyrefly: ignore[bad-argument-type]
    assert sorted(f.suggested_fix or "" for f in findings) == [
        '"for 9 months"',
        '"then 21.21%\u201328.28% variable APR"',
    ]


def test_a_variable_card_apr_never_gets_a_fixed_period_suggestion() -> None:
    text = "Fixed rate card. 21.21%\u201328.28% variable APR. $95 annual fee."
    assert _fix(text, "card.fixed_apr", product=Product.CREDIT_CARD, terms=CC) is None


def test_issuer_line_has_one_period_and_a_plain_citation() -> None:
    [finding] = [
        f
        for f in run_code_checks(make_ctx("$95 annual fee.", product=Product.CREDIT_CARD, terms=CC)).findings
        if f.rule_id == "card.issuer_line"
    ]
    assert finding.suggested_fix == '"The ClearPath Card is issued by Harborview Bank, N.A."'
    assert finding.citation == "ClearPath card program policy"


def test_deferred_interest_suggestions_reuse_the_copys_period() -> None:
    card = {"product": Product.CREDIT_CARD, "terms": CC}
    findings = [
        f
        for f in run_code_checks(make_ctx("No interest for 6 months on purchases over $199.", **card)).findings  # pyrefly: ignore[bad-argument-type]
        if f.rule_id == "card.deferred_interest"
    ]
    assert findings
    for f in findings:
        assert f.suggested_fix is not None
        assert "6 months" in f.suggested_fix
        assert "12" not in f.suggested_fix


def test_closed_end_apr_suggestion_uses_the_terms_and_none_without_them() -> None:
    assert _fix("Borrow $5,000 over 36 months.", "closed_end.trigger_apr", terms=PL) == (
        'Add the APR, e.g. "11.11%\u201333.33% APR".'
    )
    no_terms = {"product": Product.MORTGAGE_PREQUAL, "terms": None, "channel": Channel.DISPLAY}
    assert _fix("Pay just $1,450 a month for 30 years.", "closed_end.trigger_apr", **no_terms) is None


def test_repayment_suggestion_is_computed_from_the_copy() -> None:
    # $10,000 at 12.99% over 36 months: $336.90 a month.
    text = "Borrow $10,000 at 12.99% APR over 36 months."
    assert _fix(text, "closed_end.trigger_repayment", terms=PL) == '"36 monthly payments of $337"'
    assert _fix("Personal loans with 60-month terms at 12.99% APR.", "closed_end.trigger_repayment", terms=PL) is None


def test_down_payment_suggestion_invents_no_percentage() -> None:
    text = "Finance 100% of your home. 6.5% APR over 30 years."
    product = {"product": Product.MORTGAGE_PREQUAL, "terms": None}
    assert _fix(text, "closed_end.trigger_downpayment", **product) is None


def test_postal_address_suggestion_is_the_configured_company_address() -> None:
    email = {"channel": Channel.EMAIL}
    assert _fix("Personal loans. Unsubscribe.", "email.postal_address", **email) == (
        '"ClearPath Financial, Inc., 500 Market Street, Suite 1200, San Francisco, CA 94105"'
    )


def test_arm_suggestions_take_the_fixed_period_from_the_named_arm() -> None:
    mtg = {"product": Product.MORTGAGE_PREQUAL, "terms": None}
    assert _fix("Our 7/6 ARM: the rate is fixed.", "mortgage.arm_fixed", **mtg) == (
        '"fixed for the first 7 years, then may adjust"'
    )
    assert _fix("Fixed payments on our 10/6 ARM.", "mortgage.arm_fixed", **mtg) == (
        '"10/6 ARM: rate fixed for the first 10 years, then may adjust"'
    )
    assert _fix("Adjustable-rate mortgage. The rate is fixed.", "mortgage.arm_fixed", **mtg) is None
