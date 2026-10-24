import pytest

from checks.engine import run_code_checks
from core.domain import Channel, FixKind, Product, Severity

from .conftest import codes, make_ctx, quotes

MTG = Product.MORTGAGE_PREQUAL
TAXES = "Payments do not include taxes and insurance; the actual payment obligation will be greater."


def mtg(text: str, **kw: object) -> set[str]:
    return codes(run_code_checks(make_ctx(text, product=MTG, **kw)))  # type: ignore[arg-type]


def test_fixed_before_arm_term() -> None:
    result = run_code_checks(make_ctx("Fixed for 5 years! Then it adjusts. 5/1 ARM.", product=MTG))
    assert quotes(result, "mortgage.arm_fixed") == ["Fixed"]


def test_each_fixed_needs_period_and_may_change() -> None:
    text = "Our 5/1 Adjustable-Rate Mortgage: the rate is fixed."
    assert quotes(run_code_checks(make_ctx(text, product=MTG)), "mortgage.arm_fixed") == ["fixed"]


def test_compliant_arm_fixed_statement() -> None:
    text = "5/1 ARM: the rate is fixed for the first 5 years, then may adjust annually."
    assert "mortgage.arm_fixed" not in mtg(text)


def test_fixed_rate_mortgage_without_arm_context() -> None:
    assert "mortgage.arm_fixed" not in mtg("Lock in a 30-year fixed rate today.")


def test_payment_needs_taxes_and_insurance_statement() -> None:
    result = run_code_checks(make_ctx("Payments from $1,450/mo on a 30-year loan at 6.41% APR.", product=MTG))
    assert quotes(result, "mortgage.payment_taxes_insurance") == ["$1,450"]


def test_taxes_statement_in_a_footnote_paragraph_does_not_count() -> None:
    text = f"Payments from $1,450/mo* on a 30-year loan at 6.41% APR.\n\n* {TAXES}"
    result = run_code_checks(make_ctx(text, product=MTG))
    (finding,) = [f for f in result.findings if f.rule_id == "mortgage.payment_taxes_insurance"]
    assert "next to" in finding.message


def test_taxes_statement_next_to_payment() -> None:
    text = f"Payments from $1,450/mo on a 30-year loan at 6.41% APR. {TAXES}"
    assert "mortgage.payment_taxes_insurance" not in mtg(text)


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("Apply for our government loan program.", "government loan program"),
        ("A government-backed path to homeownership.", "government-backed"),
        ("FHA loans with low down payments.", "FHA"),
        ("VA loans for veterans.", "VA loans"),
        ("Approved by HUD.", "HUD"),
    ],
)
def test_government_affiliation(text: str, quote: str) -> None:
    assert quotes(run_code_checks(make_ctx(text, product=MTG)), "mortgage.government") == [quote]


def test_postal_abbreviation_va_is_not_government() -> None:
    text = "ClearPath Home Loans, 100 Main St, Richmond, VA 23219."
    assert "mortgage.government" not in mtg(text, channel=Channel.EMAIL)


def test_non_affiliation_statement_is_not_flagged() -> None:
    assert "mortgage.government" not in mtg("ClearPath is not affiliated with any government agency.")


@pytest.mark.parametrize(
    "text",
    [
        "Wipe-Out Personal Debts!",
        "New DEBT-FREE Payment",
        "Set yourself free; get out of debt today",
        "Refinance today and wipe your debt clean!",
        "Get yourself out of debt * * * Forever!",
        "Pre-payment Penalty Waiver.",
    ],
)
def test_comment_24i3_debt_elimination_examples(text: str) -> None:
    assert "mortgage.debt_elimination" in mtg(text)


@pytest.mark.parametrize(
    "text",
    ["Consolidate your debt into one payment.", "Reduce your monthly debt payments.", "Pay off debt faster."],
)
def test_legitimate_debt_statements(text: str) -> None:
    assert "mortgage.debt_elimination" not in mtg(text)


def test_counselor() -> None:
    assert quotes(run_code_checks(make_ctx("Talk to a mortgage counselor.", product=MTG)), "mortgage.counselor") == [
        "counselor"
    ]
    assert "mortgage.counselor" not in mtg("Talk to a loan officer.")


def test_mortgage_rules_do_not_run_on_personal_loans() -> None:
    result = run_code_checks(make_ctx("Wipe out your debts with an FHA-style loan. Talk to a counselor."))
    assert not {c for c in codes(result) if c.startswith("mortgage.")}


@pytest.mark.parametrize(
    ("text", "quote", "replacement"),
    [
        ("Get pre-approved for a mortgage in minutes.", "Get pre-approved", "Get prequalified"),
        ("Get preapproved today.", "Get preapproved", "Get prequalified"),
        ("Be pre approved before you house-hunt.", "Be pre approved", "Be prequalified"),
        ("Start your mortgage pre-approval online.", "pre-approval", "prequalification"),
    ],
)
def test_preapproval_invitation_on_a_prequal_product_is_a_warning(text: str, quote: str, replacement: str) -> None:
    result = run_code_checks(make_ctx(text, product=MTG))
    (finding,) = [f for f in result.findings if f.rule_id == "mortgage.preapproval_offer"]
    assert finding.quote == quote
    assert finding.severity == Severity.WARNING
    assert (finding.fix_kind, finding.replacement_text) == (FixKind.REPLACE, replacement)  # the copy's own wording
    assert finding.suggested_fix == f'"{replacement}"'
    assert "claims.preapproved" not in codes(result)


@pytest.mark.parametrize(
    "text",
    [
        "Get prequalified in minutes.",
        "See what you qualify for in minutes.",
        "Find out how much home you qualify for.",
        "Prequalification is not a commitment to lend.",
    ],
)
def test_prequalification_and_qualify_ctas_are_not_flagged(text: str) -> None:
    assert not mtg(text) & {"mortgage.preapproval_offer", "claims.preapproved"}


def test_preapproval_assertion_stays_a_blocking_claim_not_this_warning() -> None:
    found = mtg("You're pre-approved for a mortgage!")
    assert "claims.preapproved" in found
    assert "mortgage.preapproval_offer" not in found


def test_preapproval_invitation_is_not_flagged_for_personal_loans() -> None:
    result = run_code_checks(make_ctx("Get pre-approved in minutes."))
    assert not codes(result) & {"mortgage.preapproval_offer", "claims.preapproved"}
