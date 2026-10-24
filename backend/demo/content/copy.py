"""Boilerplate that real ClearPath copy repeats: license lines, footers, disclosures."""

from typing import Final

CFL_LINE: Final = "Loans made or arranged pursuant to a California Financing Law license, #60DBO-184027."
CRMLA_LINE: Final = (
    "ClearPath Home Lending is licensed by the Department of Financial Protection and Innovation under the "
    "California Residential Mortgage Lending Act, license #41DBO-97215."
)
ADDRESS: Final = "ClearPath Financial, Inc., 500 Market Street, Suite 1200, San Francisco, CA 94105"
EMAIL_FOOTER: Final = (
    "This is an advertisement from ClearPath Financial. You're receiving this because you opted in to offers at "
    "clearpath.example. Unsubscribe or manage your email preferences at clearpath.example/prefs.\n" + ADDRESS
)
ISSUER_LINE: Final = (
    "The ClearPath Card is issued by Harborview Bank, N.A., Member FDIC, pursuant to a license from Visa."
)
SOFT_PULL: Final = (
    "Checking your rate won't affect your credit score. If you continue and apply, we'll do a hard credit inquiry."
)
SUBJECT_TO_APPROVAL: Final = "Subject to credit approval."


def pl_range(floor: str) -> str:
    return (
        f"Fixed APRs from {floor}% to 35.99%. Your rate depends on your credit history, income and other factors; "
        "the lowest rates go to the most creditworthy applicants."
    )


def card_terms(low: str, high: str) -> str:
    return (
        f"0% intro APR on purchases for 15 months from account opening, then a variable APR of {low}% to {high}% "
        "based on your creditworthiness. $0 annual fee. Balance transfer fee: 3% of each transfer (min $5)."
    )
