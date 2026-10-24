from decimal import ROUND_HALF_UP, Decimal

import pytest

from checks.engine import Span, TermsRefDraft, render_fast_track, run_code_checks
from checks.engine.amortization import monthly_payment
from core.domain import Product

from .conftest import cc_terms, codes, make_ctx, pl_terms

PL_AD = (
    "ClearPath personal loans: APRs from 7.49% to 35.99%. Borrow $1,000 to $50,000.\n\n"
    "Example: a $10,000 loan over 36 months at 12.99% APR has 36 monthly payments of $337."
)


def stored_refs(text: str, product: Product = Product.PERSONAL_LOAN) -> list[TermsRefDraft]:
    """What workstream F persists and rebuilds: field, span, quoted value; nothing else."""
    result = run_code_checks(make_ctx(text, product=product))
    return [TermsRefDraft(r.field, Span(r.span.start, r.span.end), r.quoted_value) for r in result.terms_refs]


def test_amortization_matches_the_worked_example() -> None:
    assert monthly_payment(Decimal(10000), Decimal("12.99"), 36).quantize(Decimal(1), ROUND_HALF_UP) == 337


def test_amortization_zero_rate_divides_evenly() -> None:
    assert monthly_payment(Decimal(1200), Decimal(0), 12) == 100


def test_replaces_only_the_referenced_numbers() -> None:
    out = render_fast_track(PL_AD, stored_refs(PL_AD), pl_terms(apr_min=Decimal("7.99"), amount_max=Decimal(40000)))
    assert out == PL_AD.replace("7.49%", "7.99%").replace("$50,000", "$40,000")


def test_example_at_the_floor_rate_moves_with_the_floor_and_recomputes_payment() -> None:
    text = "Example: $10,000 for 36 months at 7.49% APR = $311/mo."
    out = render_fast_track(text, stored_refs(text), pl_terms(apr_min=Decimal("12.99")))
    assert out == "Example: $10,000 for 36 months at 12.99% APR = $337/mo."


def test_payment_keeps_cents_when_the_original_had_them() -> None:
    text = "Example: $10,000 for 36 months at 7.49% APR = $311.02/mo."
    out = render_fast_track(text, stored_refs(text), pl_terms(apr_min=Decimal("12.99")))
    assert out.endswith("= $336.89/mo.")


def test_new_rate_is_never_rounded_to_the_original_precision() -> None:
    text = "Rates as low as 8% APR."
    refs = [TermsRefDraft("apr_min", Span(16, 18), Decimal(8))]
    assert render_fast_track(text, refs, pl_terms(apr_min=Decimal("7.49"))) == "Rates as low as 7.49% APR."


def test_new_rate_keeps_the_original_decimals() -> None:
    text = "Rates as low as 7.50% APR."
    refs = [TermsRefDraft("apr_min", Span(16, 21), Decimal("7.50"))]
    assert render_fast_track(text, refs, pl_terms(apr_min=Decimal(8))) == "Rates as low as 8.00% APR."


def test_removed_term_length_moves_to_the_nearest_bound() -> None:
    text = "Repayment terms of 24 to 60 months."
    out = render_fast_track(text, stored_refs(text), pl_terms(term_months=(36, 48, 72)))
    assert out == "Repayment terms of 36 to 72 months."


def test_dropped_intro_offer_leaves_text_for_checks_to_flag() -> None:
    text = "0% intro APR for 15 months, then 19.99%\u201329.99% variable APR. Issued by Lakeside Bank."
    new_terms = cc_terms(intro_apr=None, intro_months=None)
    out = render_fast_track(text, stored_refs(text, Product.CREDIT_CARD), new_terms)
    assert out == text
    flagged = run_code_checks(make_ctx(out, product=Product.CREDIT_CARD, terms=new_terms))
    assert "pricing.terms_available" in codes(flagged)


def test_no_annual_fee_becomes_the_new_fee() -> None:
    text = "No annual fee. Issued by Lakeside Bank."
    out = render_fast_track(text, stored_refs(text, Product.CREDIT_CARD), cc_terms(annual_fee=Decimal(95)))
    assert out == "$95 annual fee. Issued by Lakeside Bank."


def test_no_origination_fee_becomes_the_new_maximum() -> None:
    text = "No origination fees on any loan."
    out = render_fast_track(text, stored_refs(text), pl_terms(origination_fee_max_pct=Decimal(6)))
    assert out == "Origination fees up to 6% on any loan."


def test_stale_ref_is_rejected() -> None:
    with pytest.raises(ValueError, match="quoted"):
        render_fast_track(PL_AD, [TermsRefDraft("apr_min", Span(0, 5), Decimal("7.49"))], pl_terms())


def test_overlapping_refs_are_rejected() -> None:
    refs = stored_refs(PL_AD)
    with pytest.raises(ValueError, match="overlap"):
        render_fast_track(PL_AD, [refs[0], refs[0]], pl_terms())


def test_unknown_field_is_rejected() -> None:
    (first, *_) = stored_refs(PL_AD)
    with pytest.raises(ValueError, match="field"):
        render_fast_track(PL_AD, [TermsRefDraft("purchase_apr_min", first.span, first.quoted_value)], pl_terms())


def test_rendered_text_is_consistent_under_the_new_terms() -> None:
    new_terms = pl_terms(apr_min=Decimal("8.49"), apr_max=Decimal("34.99"))
    out = render_fast_track(PL_AD, stored_refs(PL_AD), new_terms)
    after = run_code_checks(make_ctx(out, terms=new_terms))
    assert not {c for c in codes(after) if c.startswith(("pricing.terms", "closed_end.example"))}
