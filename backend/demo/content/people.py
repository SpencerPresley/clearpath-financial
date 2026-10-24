"""ClearPath's compliance team, its marketers, its partners, and its offer terms.

Names match the legacy tracker (`scripts/generate_sample_tracker.py`), so an imported row's "Dana Kim" is the same
Dana Kim who reviews native items, and partner history joins tracker rows with items reviewed in the tool.
"""

from datetime import date
from decimal import Decimal
from typing import Final

from core.domain import CreditCardTerms, PartnerType, PersonalLoanTerms, Product, Role
from demo.story import PartnerSpec, Persona, TermsSpec, day

PERSONAS: Final = (
    # The four documented logins, one per role.
    Persona("priya", "marketer@clearpath.demo", "Priya Natarajan", (Role.MARKETER,), "Growth Marketing (PL)"),
    Persona("dana", "reviewer@clearpath.demo", "Dana Kim", (Role.REVIEWER,), "Marketing Compliance"),
    Persona("rachel", "lead@clearpath.demo", "Rachel Okafor", (Role.LEAD,), "Marketing Compliance (lead)"),
    Persona("admin", "admin@clearpath.demo", "Avery Chen", (Role.ADMIN,), "Business Systems"),
    # The rest of the review team, so assignment and workload are visible.
    Persona("sam", "sam@clearpath.demo", "Samuel Ortega", (Role.REVIEWER,), "Marketing Compliance"),
    Persona("leah", "leah@clearpath.demo", "Leah Brandt", (Role.REVIEWER,), "Marketing Compliance"),
    Persona("nikhil", "nikhil@clearpath.demo", "Nikhil Rao", (Role.REVIEWER,), "Marketing Compliance"),
    # Other submitters.
    Persona("marcus", "marcus@clearpath.demo", "Marcus Bell", (Role.MARKETER,), "Card Marketing"),
    Persona("elena", "elena@clearpath.demo", "Elena Ruiz", (Role.MARKETER,), "Mortgage Marketing"),
    Persona("jordan", "jordan@clearpath.demo", "Jordan Whitfield", (Role.MARKETER,), "Partnerships & Affiliates"),
    Persona("hannah", "hannah@clearpath.demo", "Hannah Cho", (Role.MARKETER,), "Lifecycle & CRM"),
)


def _agreement(partner: str, kind: str, signed: str, *, extra: str = "") -> str:
    return (
        f"MARKETING PARTNER AGREEMENT (summary for compliance review)\n\n"
        f"Parties: ClearPath Financial, Inc. and {partner}.\n"
        f"Relationship: {kind}. Signed {signed}.\n\n"
        "1. Compensation. ClearPath pays the partner per funded loan or approved card account. The partner must "
        "disclose this compensation clearly and near the top of any page, email, or post that mentions ClearPath.\n"
        "2. Pre-approval of content. Every creative that names ClearPath or quotes its rates, fees, or terms is "
        "submitted to ClearPath Marketing Compliance and runs only as approved. Changes need a new approval.\n"
        "3. Rates and terms. The partner quotes only the ClearPath offer terms in effect and updates them within "
        "5 business days of notice. No representative examples other than ClearPath's.\n"
        "4. Prohibited claims. No guaranteed approval, no pre-approval or pre-selection language without a "
        "ClearPath prescreen file, no claims that applying has no effect on credit, no government affiliation.\n"
        "5. Monitoring. ClearPath may capture the partner's pages at any time and may require takedown within "
        "1 business day.\n"
        f"{extra}"
    )


PARTNERS: Final = (
    PartnerSpec(
        key="lendcompare",
        name="LendCompare",
        type=PartnerType.MARKETPLACE,
        website="https://lendcompare.example",
        contact_email="partnerships@lendcompare.example",
        agreement_signed_on=date(2024, 3, 18),
        notes="Top PL volume partner. Quarterly screenshot audit.",
        agreement=_agreement("LendCompare, LLC", "comparison marketplace (PL and card)", "March 18, 2024"),
    ),
    PartnerSpec(
        key="rateradar",
        name="RateRadar",
        type=PartnerType.MARKETPLACE,
        website="https://rateradar.example",
        contact_email="affiliates@rateradar.example",
        agreement_signed_on=date(2024, 9, 9),
        notes="Loan rate comparison site. Listings refresh from our rate feed weekly.",
        agreement=_agreement("RateRadar Inc.", "rate comparison marketplace (PL)", "September 9, 2024"),
    ),
    PartnerSpec(
        key="cardperks",
        name="CardPerks Weekly",
        type=PartnerType.AFFILIATE,
        website="https://cardperksweekly.example",
        contact_email="editor@cardperksweekly.example",
        agreement_signed_on=date(2025, 2, 3),
        notes="Newsletter sends need our review too, not just the site.",
        agreement=_agreement("CardPerks Media", "affiliate publisher (card)", "February 3, 2025"),
    ),
    PartnerSpec(
        key="maya",
        name="Money with Maya",
        type=PartnerType.INFLUENCER,
        website="https://moneywithmaya.example",
        contact_email="maya@moneywithmaya.example",
        agreement_signed_on=date(2025, 8, 21),
        notes="Warning letter 3/2026 re: missing #ad on two posts.",
        agreement=_agreement(
            "Maya Torres (Money with Maya)",
            "paid influencer (PL and card), Instagram and TikTok",
            "August 21, 2025",
            extra=(
                '6. Disclosure wording. Every post opens with "#ad" or "Paid partnership with ClearPath" in the '
                "first line of the caption and as an on-screen label for the full video.\n"
            ),
        ),
    ),
    PartnerSpec(
        key="leadstream",
        name="LeadStream Direct",
        type=PartnerType.LEAD_GEN,
        website="https://leadstreamdirect.example",
        contact_email="compliance@leadstreamdirect.example",
        agreement_signed_on=date(2024, 6, 12),
        notes="Commission hold 7/2026-8/2026 after an unapproved SMS went out.",
        agreement=_agreement(
            "LeadStream Direct LLC",
            "lead generator (PL), email and SMS to its own opted-in lists",
            "June 12, 2024",
            extra="6. Consent. The partner keeps TCPA consent records for every number it texts and provides them "
            "on request within 2 business days.\n",
        ),
    ),
    PartnerSpec(
        key="finmatch",
        name="FinMatch",
        type=PartnerType.MARKETPLACE,
        website="https://finmatch.example",
        contact_email="partners@finmatch.example",
        agreement_signed_on=date(2025, 5, 14),
        notes="Loan marketplace with soft-pull prequal.",
        agreement=_agreement(
            "FinMatch Technologies", "marketplace with soft-pull prequalification (PL)", "May 14, 2025"
        ),
    ),
    PartnerSpec(
        key="homebound",
        name="HomeBound Leads",
        type=PartnerType.LEAD_GEN,
        website="https://homeboundleads.example",
        contact_email="ops@homeboundleads.example",
        agreement_signed_on=date(2025, 10, 1),
        notes="Warm-transfer scripts go through us before every refresh.",
        agreement=_agreement(
            "HomeBound Leads, Inc.",
            "mortgage lead generator (CA), co-branded pages and warm transfers",
            "October 1, 2025",
        ),
    ),
    PartnerSpec(
        key="goldenstate",
        name="Golden State Saver",
        type=PartnerType.AFFILIATE,
        website="https://goldenstatesaver.example",
        contact_email="hello@goldenstatesaver.example",
        agreement_signed_on=date(2026, 1, 15),
        notes="Onboarded 1/2026; sent the disclosure kit.",
        agreement=_agreement("Golden State Saver Media", "affiliate publisher (California)", "January 15, 2026"),
    ),
    # The two partners whose pages ClearPath hosts for the drift demo (drift.demo.PAGES); LendCompare is the third.
    PartnerSpec(
        key="cardscout",
        name="CardScout",
        type=PartnerType.AFFILIATE,
        website="https://cardscout.example",
        contact_email="partners@cardscout.example",
        agreement_signed_on=date(2026, 8, 3),
        notes="Card review site. Signed for the Card relaunch; review page monitored daily.",
        agreement=_agreement("CardScout Media, Inc.", "affiliate publisher (card reviews)", "August 3, 2026"),
    ),
    PartnerSpec(
        key="budgetbee",
        name="BudgetBee",
        type=PartnerType.AFFILIATE,
        website="https://budgetbee.example",
        contact_email="sponsorships@budgetbee.example",
        agreement_signed_on=date(2026, 9, 14),
        notes="Personal finance blog. Sponsored articles only; copy must run as approved.",
        agreement=_agreement(
            "BudgetBee Publishing LLC", "affiliate publisher (sponsored articles)", "September 14, 2026"
        ),
    ),
)


_PL_BASE: Final = {
    "apr_max": Decimal("35.99"),
    "amount_min": Decimal(1000),
    "amount_max": Decimal(50000),
    "term_months": (24, 36, 48, 60),
    "origination_fee_min_pct": Decimal(0),
    "origination_fee_max_pct": Decimal(8),
}
_CC_BASE: Final = {
    "purchase_apr_variable": True,
    "intro_apr": Decimal(0),
    "intro_months": 15,
    "balance_transfer_fee_pct": Decimal(3),
    "annual_fee": Decimal(0),
    "issuing_bank": "Harborview Bank, N.A.",
}

# The terms in force at go-live are entered that morning: the PL floor is 9.49%, where the tracker's 6/1/26 rate
# sheet left it (the 8.99% era lives in the imported tracker). The demo adds a change six days before the seed so a
# terms-change re-review with fast-track versions is waiting in the queue. day(68) is go-live morning
# (demo/content/calendar.py GO_LIVE, 08:00); test_seed checks nothing native predates it.
PL_FLOOR_NOW: Final = Decimal("9.99")
TERMS: Final = (
    TermsSpec(
        Product.PERSONAL_LOAN,
        day(68, "08:30"),
        PersonalLoanTerms.model_validate({**_PL_BASE, "apr_min": Decimal("9.49")}),
        "Rate sheet of 6/1/26 (APR floor 9.49%), carried over from the tracker at go-live.",
    ),
    TermsSpec(
        Product.CREDIT_CARD,
        day(68, "08:40"),
        CreditCardTerms.model_validate(
            {**_CC_BASE, "purchase_apr_min": Decimal("24.99"), "purchase_apr_max": Decimal("33.99")}
        ),
        "Harborview program terms, carried over from the tracker at go-live.",
    ),
    TermsSpec(
        Product.CREDIT_CARD,
        day(20, "08:05"),
        CreditCardTerms.model_validate(
            {**_CC_BASE, "purchase_apr_min": Decimal("24.74"), "purchase_apr_max": Decimal("33.74")}
        ),
        "Prime rate down 25 bps; Harborview moved the variable purchase APRs with it.",
    ),
    TermsSpec(
        Product.PERSONAL_LOAN,
        day(6, "08:10"),
        PersonalLoanTerms.model_validate({**_PL_BASE, "apr_min": PL_FLOOR_NOW}),
        "Rate sheet update: APR floor 9.49% to 9.99% after the warehouse line repriced. Max APR unchanged.",
    ),
)
