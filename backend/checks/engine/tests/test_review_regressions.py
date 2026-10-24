"""Regressions from the fresh review (docs/plan/reviews/rules-engine.md). Test names carry the finding id."""

from decimal import Decimal

import pytest

from checks.engine import RULES, Span, StaleTermsRef, TermsRefDraft, human_checklist, render_fast_track, run_code_checks
from checks.engine.registry import ENGINE_VERSION
from core.domain import AttachmentKind, Channel, Product

from .conftest import cc_terms, codes, make_ctx, pl_terms, quotes

CC = Product.CREDIT_CARD
MTG = Product.MORTGAGE_PREQUAL
ISSUER = " Issued by Lakeside Bank."
TWO_EXAMPLES = (
    "APRs 7.49%\u201335.99%. Example: A $10,000 loan at 12.99% APR for 36 months has monthly payments of $337. "
    "A $20,000 loan at 15.99% APR for 60 months has monthly payments of $486."
)


def refs_of(text: str, product: Product = Product.PERSONAL_LOAN) -> list[TermsRefDraft]:
    return list(run_code_checks(make_ctx(text, product=product)).terms_refs)


def test_h1_two_examples_in_one_paragraph_keep_their_own_parts() -> None:
    assert "closed_end.example_payment" not in codes(run_code_checks(make_ctx(TWO_EXAMPLES)))
    out = render_fast_track(TWO_EXAMPLES, refs_of(TWO_EXAMPLES), pl_terms(apr_min=Decimal("7.99")))
    assert out == TWO_EXAMPLES.replace("7.49%", "7.99%")


def test_h1_payment_stated_before_its_parts() -> None:
    text = "Example: monthly payments of $337 for a $10,000 loan over 36 months at 12.99% APR."
    assert "closed_end.example_payment" not in codes(run_code_checks(make_ctx(text)))
    assert [r.field for r in refs_of(text)] == ["example_payment"]


def test_h1_payment_headline_with_the_example_in_the_next_sentence() -> None:
    text = "Pay just $311/mo. Example: $10,000 over 36 months at 7.49% APR. APRs 7.49%\u201335.99%."
    out = render_fast_track(text, refs_of(text), pl_terms(apr_min=Decimal("12.99")))
    assert out == "Pay just $337/mo. Example: $10,000 over 36 months at 12.99% APR. APRs 12.99%\u201335.99%."


def test_intro_months_stay_in_the_intro_sentence() -> None:
    text = "0% intro APR on purchases. Plus 5% cash back on dining for 6 months." + ISSUER
    assert "intro_months" not in [r.field for r in refs_of(text, CC)]


def test_h2_number_of_payments_phrasing_is_an_example() -> None:
    wrong = "Example: borrow $10,000 and repay in 36 monthly payments of $350 at 12.99% APR."
    assert quotes(run_code_checks(make_ctx(wrong)), "closed_end.example_payment") == ["$350"]
    right = wrong.replace("$350", "$337")
    assert [r.field for r in refs_of(right)] == ["example_payment"]


@pytest.mark.parametrize(
    "text",
    [
        "Pay your balance in full each month and pay no interest on purchases.",
        "Pay no interest for 15 months with a 0% intro APR on purchases, then 19.99%\u201329.99% variable APR.",
        (
            "If paid in full within 12 months, pay no interest. Interest will be charged to your account from the "
            "purchase date if the promotional balance is not paid in full within 12 months."
        ),
    ],
)
def test_h3_grace_period_intro_apr_and_leading_if_paid_in_full_are_not_deferred_interest_problems(text: str) -> None:
    assert "card.deferred_interest" not in codes(run_code_checks(make_ctx(text + ISSUER, product=CC)))


@pytest.mark.parametrize(
    "text",
    [
        "See what you qualify for in minutes.",
        "Find out how much you qualify for.",
        "Once you qualify, funds arrive as soon as tomorrow.",
    ],
)
def test_h4_qualification_ctas_are_not_preapproval_claims(text: str) -> None:
    assert "claims.preapproved" not in codes(run_code_checks(make_ctx(text)))


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("No paperwork, pre-approved in minutes.", "claims.preapproved"),
        ("No fees, guaranteed approval.", "claims.guaranteed"),
    ],
)
def test_m1_negation_does_not_cross_a_comma(text: str, rule: str) -> None:
    assert rule in codes(run_code_checks(make_ctx(text)))


def test_m2_years_in_business_are_not_a_loan_term() -> None:
    text = "Trusted by borrowers for over 10 years. Personal loans 7.49%\u201335.99% APR."
    found = codes(run_code_checks(make_ctx(text)))
    assert "closed_end.trigger_repayment" not in found
    assert "pricing.terms_available" not in found


@pytest.mark.parametrize(
    "text",
    [
        "Consolidate and save up to $200 a month.",
        "Pay $0 in origination fees.",
        "Refer a friend and get $100.",
    ],
)
def test_m3_savings_fees_and_bonuses_are_not_payments_or_amounts(text: str) -> None:
    found = codes(run_code_checks(make_ctx(text)))
    assert not found & {"closed_end.trigger_repayment", "closed_end.trigger_apr", "pricing.terms_available"}


def test_m3_comparative_percent_is_not_a_rate() -> None:
    found = codes(run_code_checks(make_ctx("Our rates are 2% lower than the big banks.")))
    assert not found & {"closed_end.other_rate", "closed_end.apr_label", "pricing.terms_available"}


def test_m4_card_apr_below_the_floor_is_out_of_range_not_intro() -> None:
    result = run_code_checks(make_ctx("15.99% variable APR. $0 annual fee." + ISSUER, product=CC))
    assert codes(result) == {"pricing.terms_available"}
    assert "intro_apr" not in [r.field for r in result.terms_refs]


def test_m5_first_year_annual_fee_waiver() -> None:
    text = "$0 annual fee for the first year, then $95. 19.99%\u201329.99% variable APR." + ISSUER
    terms = cc_terms(annual_fee=Decimal(95))
    result = run_code_checks(make_ctx(text, product=CC, terms=terms))
    assert "pricing.terms_available" not in codes(result)
    out = render_fast_track(text, list(result.terms_refs), cc_terms(annual_fee=Decimal(99)))
    assert out == text.replace("then $95", "then $99")


def test_m6_term_bounds_move_with_the_new_bounds() -> None:
    text = "Terms from 24 to 60 months."
    new = pl_terms(term_months=(12, 24, 36, 48, 60, 72))
    out = render_fast_track(text, refs_of(text), new)
    assert out == "Terms from 12 to 72 months."
    assert "pricing.terms_current" not in codes(run_code_checks(make_ctx(out, terms=new)))


def test_m7_every_listed_term_is_checked() -> None:
    text = "Choose terms of 24, 36, 48, or 60 months."
    result = run_code_checks(make_ctx(text, terms=pl_terms(term_months=(36, 48, 60))))
    assert quotes(result, "pricing.terms_available") == ["24"]


def test_l1_one_qualifier_finding_per_range() -> None:
    assert (
        len(quotes(run_code_checks(make_ctx("Rates from 7.49% to 35.99% APR.")), "pricing.creditworthiness_qualifier"))
        == 1
    )


@pytest.mark.parametrize(
    "address",
    ["One Market Plaza, Suite 400, San Francisco, CA 94105", "4 Embarcadero Center, San Francisco, CA 94111"],
)
def test_l3_common_addresses_count(address: str) -> None:
    text = f"This is an advertisement. Unsubscribe. ClearPath Financial, {address}."
    assert "email.postal_address" not in codes(run_code_checks(make_ctx(text, channel=Channel.EMAIL)))


def test_l4_disclaimers_and_counseling_referrals() -> None:
    disclaimer = "ClearPath is not affiliated with HUD or FHA and does not offer VA loans."
    assert "mortgage.government" not in codes(run_code_checks(make_ctx(disclaimer, product=MTG)))
    referral = "Contact a HUD-approved housing counselor for free advice."
    assert not codes(run_code_checks(make_ctx(referral, product=MTG))) & {"mortgage.government", "mortgage.counselor"}


def test_arm_and_fixed_products_in_one_ad() -> None:
    text = (
        "Compare a 30-year fixed with our 5/1 ARM. 5/1 ARM rate fixed for the first 5 years, then may adjust annually."
    )
    assert "mortgage.arm_fixed" not in codes(run_code_checks(make_ctx(text, product=MTG)))


def test_reg_n_is_not_the_lead_citation_outside_mortgages() -> None:
    for rule_id in ("claims.preapproved", "claims.guaranteed"):
        assert not RULES[rule_id].citation.startswith("Reg N")


@pytest.mark.parametrize("text", ["30-day rate lock guarantee.", "Your rate is guaranteed for the life of the loan."])
def test_rate_guarantees_are_not_approval_guarantees(text: str) -> None:
    assert "claims.guaranteed" not in codes(run_code_checks(make_ctx(text)))


def test_get_preapproved_cta_is_not_a_claim() -> None:
    assert "claims.preapproved" not in codes(run_code_checks(make_ctx("Get pre-approved in minutes.", product=MTG)))


def test_stale_refs_raise_a_typed_error() -> None:
    with pytest.raises(StaleTermsRef):
        render_fast_track("Rates from 7.49% APR.", [TermsRefDraft("apr_min", Span(11, 16), Decimal(1))], pl_terms())
    assert issubclass(StaleTermsRef, ValueError)


def test_no_rule_drops_out_for_a_back_dated_context() -> None:
    from datetime import date

    early = {
        f.rule_id
        for f in run_code_checks(make_ctx("Guaranteed approval. No credit check.", today=date(2026, 1, 1))).findings
    }
    assert {"claims.guaranteed", "claims.credit_impact"} <= early


def test_engine_version_is_exported_for_cache_keys() -> None:
    assert isinstance(ENGINE_VERSION, str)
    assert ENGINE_VERSION


@pytest.mark.parametrize("text", ["", "   ", "\n\n", "%", "$", "-"])
@pytest.mark.parametrize("product", list(Product))
@pytest.mark.parametrize("channel", [Channel.EMAIL, Channel.SMS, Channel.AFFILIATE_PAGE])
def test_first_keystroke_states_never_raise(text: str, product: Product, channel: Channel) -> None:
    result = run_code_checks(make_ctx(text, product=product, channel=channel))
    assert human_checklist(make_ctx(text, product=product, channel=channel))
    assert all(f.span is None or f.quote == text[f.span.start : f.span.end] for f in result.findings)
    assert result.terms_refs == ()


def test_unused_attachment_kinds_do_not_change_results() -> None:
    text = "Guaranteed approval!"
    plain = run_code_checks(make_ctx(text))
    with_creative = run_code_checks(make_ctx(text, attachments=(AttachmentKind.CREATIVE,)))
    assert plain == with_creative
