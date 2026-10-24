import pytest

from checks.engine import run_code_checks
from core.domain import Product

from .conftest import cc_terms, codes, make_ctx, quotes

CC = Product.CREDIT_CARD
ISSUER = " The ClearPath Card is issued by Lakeside Bank, Member FDIC."
COMPLIANT = (
    "0% intro APR on purchases for 15 months, then a 19.99%\u201329.99% variable APR based on your "
    "creditworthiness. $0 annual fee. 3% balance transfer fee (min $5)." + ISSUER
)


def card(text: str, **kw: object) -> set[str]:
    return codes(run_code_checks(make_ctx(text, product=CC, **kw)))  # type: ignore[arg-type]


def test_compliant_card_ad_is_clean() -> None:
    assert not {c for c in card(COMPLIANT) if c.startswith("card.")}


def test_negative_trigger_needs_apr() -> None:
    result = run_code_checks(make_ctx("No annual fee!" + ISSUER, product=CC))
    assert quotes(result, "card.trigger_apr") == ["No annual fee"]
    assert "card.trigger_annual_fee" not in codes(result)


def test_no_interest_triggers_and_billing_wording_does_not() -> None:
    assert "card.trigger_apr" in card("No interest charges until May." + ISSUER)
    assert not {c for c in card("You won't be billed until May." + ISSUER) if c.startswith("card.trigger")}


def test_rate_trigger_needs_annual_fee_statement() -> None:
    result = run_code_checks(make_ctx("19.99%\u201329.99% variable APR." + ISSUER, product=CC))
    assert quotes(result, "card.trigger_annual_fee") == ["19.99%"]


def test_variable_purchase_apr_must_say_variable() -> None:
    result = run_code_checks(make_ctx("Purchase APR 19.99%\u201329.99%. $0 annual fee." + ISSUER, product=CC))
    assert quotes(result, "card.apr_variable") == ["19.99%"]
    fixed_terms = cc_terms(purchase_apr_variable=False)
    assert "card.apr_variable" not in card(
        "Purchase APR 19.99%\u201329.99%. $0 annual fee." + ISSUER, terms=fixed_terms
    )


def test_rate_not_labeled_apr() -> None:
    result = run_code_checks(make_ctx("Interest rates from 19.99%. $0 annual fee." + ISSUER, product=CC))
    assert quotes(result, "card.apr_label") == ["19.99%"]


def test_balance_transfer_mention_without_fee_is_a_warning() -> None:
    text = "Transfer a balance and save. 19.99%\u201329.99% variable APR. $0 annual fee." + ISSUER
    result = run_code_checks(make_ctx(text, product=CC))
    assert quotes(result, "card.trigger_transaction_fees") == ["Transfer a balance"]


def test_intro_rate_without_intro_word() -> None:
    text = "0% APR for 15 months, then 19.99%\u201329.99% variable APR. $0 annual fee." + ISSUER
    result = run_code_checks(make_ctx(text, product=CC))
    assert quotes(result, "card.intro_label") == ["0%"]
    assert "card.intro_terms" not in codes(result)


def test_each_intro_listing_needs_the_label() -> None:
    text = (
        "0% intro APR for 15 months, then 19.99%\u201329.99% variable APR. $0 annual fee.\n\n"
        "Pay 0% APR for 15 months on purchases." + ISSUER
    )
    result = run_code_checks(make_ctx(text, product=CC))
    (finding,) = [f for f in result.findings if f.rule_id == "card.intro_label"]
    assert finding.span is not None
    assert finding.span.start > text.index("Pay")


def test_first_intro_listing_needs_period_and_go_to_apr_in_its_paragraph() -> None:
    text = "Enjoy a 0% intro APR!\n\nAfter that, 19.99%\u201329.99% variable APR. $0 annual fee." + ISSUER
    result = run_code_checks(make_ctx(text, product=CC))
    messages = [f.message for f in result.findings if f.rule_id == "card.intro_terms"]
    assert len(messages) == 2
    assert all(f.quote == "0%" for f in result.findings if f.rule_id == "card.intro_terms")


@pytest.mark.parametrize(
    "text",
    [
        "No interest for 12 months if paid in full.",
        "Same as cash for 6 months!",
        "Deferred interest on purchases of $299 or more.",
    ],
)
def test_deferred_interest_wording(text: str) -> None:
    assert "card.deferred_interest" in card(text + ISSUER)


def test_compliant_deferred_interest_offer() -> None:
    text = (
        "No interest if paid in full within 12 months on purchases of $299 or more. Interest will be charged to "
        "your account from the purchase date if the promotional balance is not paid in full within 12 months."
    )
    assert "card.deferred_interest" not in card(text + ISSUER)


def test_deferred_interest_needs_the_purchase_date_warning() -> None:
    text = "No interest if paid in full within 12 months on purchases of $299 or more."
    result = run_code_checks(make_ctx(text + ISSUER, product=CC))
    assert quotes(result, "card.deferred_interest") == ["No interest"]


def test_fixed_apr_needs_a_period() -> None:
    text = "A fixed APR of 14.99%. $0 annual fee." + ISSUER
    result = run_code_checks(make_ctx(text, product=CC, terms=cc_terms(purchase_apr_variable=False)))
    assert quotes(result, "card.fixed_apr") == ["fixed"]
    with_period = "A 14.99% APR, fixed for 24 months. $0 annual fee." + ISSUER
    fixed_terms = cc_terms(purchase_apr_variable=False)
    assert "card.fixed_apr" not in card(with_period, terms=fixed_terms)


def test_fixed_claim_on_variable_terms_mentions_variability() -> None:
    result = run_code_checks(make_ctx("A fixed APR of 19.99%. $0 annual fee." + ISSUER, product=CC))
    (finding,) = [f for f in result.findings if f.rule_id == "card.fixed_apr"]
    assert "variable" in finding.message


def test_issuer_line_required_with_the_terms_bank() -> None:
    assert quotes(run_code_checks(make_ctx("$0 annual fee.", product=CC)), "card.issuer_line") == [None]
    assert "card.issuer_line" in card("$0 annual fee. Issued by Another Bank.")
    assert "card.issuer_line" not in card("$0 annual fee. Card issued by Lakeside Bank.")
    assert "card.issuer_line" not in card("$0 annual fee. Issued by Lakeside Bank.", terms=None)
    assert "card.issuer_line" in card("$0 annual fee.", terms=None)


def test_card_rules_do_not_run_on_loans() -> None:
    result = run_code_checks(make_ctx("No annual fee. 0% APR for 15 months."))
    assert not {c for c in codes(result) if c.startswith("card.")}
