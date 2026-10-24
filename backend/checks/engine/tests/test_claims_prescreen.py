import pytest

from checks.engine import run_code_checks
from core.domain import AttachmentKind, Product

from .conftest import codes, make_ctx, quotes

CRITERIA = (AttachmentKind.PRESCREEN_CRITERIA,)
SUBSTANTIATION = (AttachmentKind.SUBSTANTIATION,)

SHORT_NOTICE = (
    'You can choose to stop receiving "prescreened" offers of credit from this and other companies by calling '
    "toll-free 1-888-567-8688. See PRESCREEN & OPT-OUT NOTICE below for more information about prescreened offers."
)
LONG_NOTICE = (
    "PRESCREEN & OPT-OUT NOTICE\n"
    "This prescreened offer of credit is based on information in your credit report indicating that you meet "
    "certain criteria. This offer is not guaranteed if you do not meet our criteria. If you do not want to receive "
    "prescreened offers of credit from this and other companies, call the consumer reporting agencies toll-free, "
    "1-888-567-8688; or write: Experian, PO Box 919, Allen, TX 75013."
)


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("You're pre-approved for up to $25,000!", "pre-approved"),
        ("Good news: you have been preselected for a personal loan.", "preselected"),
        ("Congratulations, you qualify for our best rate.", "you qualify"),
        ("You\u2019re approved. Claim your funds today.", "You\u2019re approved"),
    ],
)
def test_preapproval_claims_flag_without_prescreen_criteria(text: str, quote: str) -> None:
    result = run_code_checks(make_ctx(text))
    assert quotes(result, "claims.preapproved") == [quote]


@pytest.mark.parametrize(
    "text",
    [
        "See if you qualify in minutes.",
        "Check if you qualify without leaving home.",
        "Find out whether you qualify.",
        "Do you qualify? Apply today.",
        "Get prequalified for a mortgage in minutes.",
        "This is not a pre-approved offer.",
    ],
)
def test_legitimate_qualification_language_is_not_flagged(text: str) -> None:
    product = Product.MORTGAGE_PREQUAL if "mortgage" in text else Product.PERSONAL_LOAN
    assert "claims.preapproved" not in codes(run_code_checks(make_ctx(text, product=product)))


def test_preapproved_with_prescreen_criteria_is_not_flagged() -> None:
    result = run_code_checks(make_ctx("You're pre-approved!", attachments=CRITERIA))
    assert "claims.preapproved" not in codes(result)


@pytest.mark.parametrize("text", ["Guaranteed approval!", "Approval guaranteed, no matter what.", "We guarantee it."])
def test_guarantee_claims_flag(text: str) -> None:
    assert "claims.guaranteed" in codes(run_code_checks(make_ctx(text, attachments=CRITERIA)))


@pytest.mark.parametrize(
    "text", ["Approval is not guaranteed.", "There is no guarantee of approval.", "We can't guarantee approval."]
)
def test_negated_guarantees_are_not_flagged(text: str) -> None:
    assert "claims.guaranteed" not in codes(run_code_checks(make_ctx(text)))


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("No credit check required.", "No credit check"),
        ("Checking your rate won\u2019t affect your credit score.", "won\u2019t affect your credit score"),
        ("Applying will not impact your credit.", "will not impact your credit"),
        ("See offers without affecting your credit score.", "without affecting your credit score"),
        ("No impact to your credit score.", "No impact to your credit score"),
    ],
)
def test_credit_impact_claims_need_substantiation(text: str, quote: str) -> None:
    assert quotes(run_code_checks(make_ctx(text)), "claims.credit_impact") == [quote]
    assert "claims.credit_impact" not in codes(run_code_checks(make_ctx(text, attachments=SUBSTANTIATION)))


def test_credit_report_mention_alone_is_not_a_claim() -> None:
    text = "We review your credit report as part of our application process."
    assert "claims.credit_impact" not in codes(run_code_checks(make_ctx(text)))


def test_prescreen_wording_without_criteria_on_file() -> None:
    text = f"This prescreened offer is reserved for you.\n\n{SHORT_NOTICE}\n\n{LONG_NOTICE}"
    result = run_code_checks(make_ctx(text))
    assert quotes(result, "prescreen.criteria_on_file") == ["prescreened"]
    assert "prescreen.short_notice" not in codes(result)
    assert "prescreen.long_notice" not in codes(result)


def test_prescreen_criteria_attached_requires_both_notices() -> None:
    result = run_code_checks(make_ctx("You're pre-approved for a personal loan.", attachments=CRITERIA))
    assert {"prescreen.short_notice", "prescreen.long_notice"} <= codes(result)
    assert "prescreen.criteria_on_file" not in codes(result)


def test_long_notice_heading_must_be_capitalized_on_its_own_line() -> None:
    lowercase = LONG_NOTICE.replace("PRESCREEN & OPT-OUT NOTICE", "Prescreen & opt-out notice")
    text = f"{SHORT_NOTICE}\n\n{lowercase}"
    result = run_code_checks(make_ctx(text, attachments=CRITERIA))
    assert "prescreen.long_notice" in codes(result)
    assert "prescreen.short_notice" not in codes(result)


def test_short_notice_needs_toll_free_number() -> None:
    short = SHORT_NOTICE.replace("toll-free 1-888-567-8688", "us")
    result = run_code_checks(make_ctx(f"{short}\n\n{LONG_NOTICE}", attachments=CRITERIA))
    assert "prescreen.short_notice" in codes(result)


def test_complete_prescreen_mailer_is_clean() -> None:
    text = f"You've been pre-selected for a ClearPath personal loan.\n\n{SHORT_NOTICE}\n\n{LONG_NOTICE}"
    result = run_code_checks(make_ctx(text, attachments=CRITERIA))
    assert not {c for c in codes(result) if c.startswith(("prescreen.", "claims."))}


def test_non_prescreen_copy_needs_no_notices() -> None:
    result = run_code_checks(make_ctx("Personal loans for life's big moments."))
    assert not {c for c in codes(result) if c.startswith("prescreen.")}
