"""Mortgage prequalification items. No standing rate terms (spec §4.2 ruling 1): checked by rules only."""

from typing import Final

from core.domain import Channel, ItemStatus, Market
from core.domain import DecisionOutcome as O
from core.domain import Product as P
from demo.content.copy import ADDRESS, CRMLA_LINE, EMAIL_FOOTER
from demo.story import (
    Accept,
    AiFinding,
    AiResult,
    Checklist,
    Claim,
    Comment,
    Decide,
    Dismiss,
    EditFields,
    Place,
    Reaffirm,
    Resubmit,
    Story,
    Submit,
    day,
)

CA: Final = (Market.NATIONAL, Market.CA)
CRMLA_DISMISSAL: Final = (
    "Mortgage prequal is licensed under the CRMLA, not the CFL; the CRMLA license line is present. The §22162 "
    "phrase list only knows CFL wording."
)
NOT_AN_APPROVAL: Final = "Prequalification is an estimate, not a loan approval or a commitment to lend."

MTG_STORIES: Final = (
    Story(
        key="mtg-afford-lp",
        owner="elena",
        title="Mortgage LP: how much home can you afford",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.LANDING_PAGE,
        markets=CA,
        tags=("purchase",),
        first_run=-53,
        versions=(
            "How much home can you afford?\n\n"
            "Get prequalified in about 10 minutes. We'll look at your income, debts and savings to estimate a price "
            f"range and a monthly budget you're comfortable with. {NOT_AN_APPROVAL}\n\n"
            "Start my prequalification\n\n"
            f"{CRMLA_LINE}",
        ),
        steps=(
            Submit(day(57, "11:10")),
            Claim(day(56, "09:30")),
            Dismiss(day(56, "09:40"), "ca.license_disclosure", CRMLA_DISMISSAL),
            Checklist(
                day(56, "09:45"),
                notes=(("human.government_imagery", "Hero image is a family on a porch; no seals, flags or eagles."),),
            ),
            Decide(
                day(56, "09:50"), O.APPROVED, "No rates or payments; prequal described accurately; CRMLA line present."
            ),
            Place(
                day(54, "10:00"),
                "clearpath.example/home/afford",
                first_run=-53,
                url="https://clearpath.example/home/afford",
            ),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="mtg-display-wipe-debt",
        owner="elena",
        title="Refi display: wipe your debt clean",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.DISPLAY,
        tags=("refinance",),
        first_run=-14,
        versions=(
            "Refinance today and wipe your debt clean!\n"
            "Our government-backed refinance program gets you payments from $1,450/mo on a 30-year fixed loan at "
            "6.471% APR.\n"
            "Talk to a ClearPath mortgage counselor today. Get prequalified in minutes.",
        ),
        steps=(
            Submit(day(22, "15:30")),
            Claim(day(21, "10:00")),
            Accept(day(21, "10:05"), "mortgage.debt_elimination"),
            Accept(
                day(21, "10:06"),
                "mortgage.government",
                "We're not FHA-approved; nothing we offer is government-backed.",
            ),
            Accept(day(21, "10:07"), "mortgage.counselor"),
            Accept(day(21, "10:08"), "mortgage.payment_taxes_insurance"),
            Accept(day(21, "10:09"), "closed_end.trigger_downpayment"),
            Decide(
                day(21, "10:20"),
                O.REJECTED,
                "Rejected: we have no government program, our loan officers aren't counselors, and a refinance moves "
                "debt rather than eliminating it. Each of those is a prohibited claim under Reg N, so the concept "
                "can't be fixed by editing. Happy to look at a straight rate-and-payment refi ad.",
            ),
        ),
        expect=ItemStatus.REJECTED,
    ),
    Story(
        key="mtg-search-arm",
        owner="elena",
        title="Paid search: 5/6 ARM",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.PAID_SEARCH,
        tags=("arm",),
        first_run=-14,
        versions=(
            "5/6 ARM Mortgage Rates | ClearPath Home Lending\n"
            "Lock a fixed 5.875% rate on a 5/6 ARM. 6.212% APR. Get prequalified online.",
            "5/6 ARM Mortgage Rates | ClearPath Home Lending\n"
            "5/6 ARM: 6.212% APR. The rate may increase after the introductory period. Get prequalified online.",
        ),
        steps=(
            Submit(day(19, "09:20")),
            Claim(day(18, "11:00")),
            Accept(day(18, "11:05"), "mortgage.arm_fixed", "An ARM can't be called fixed."),
            Accept(day(18, "11:06"), "closed_end.rate_may_increase"),
            Accept(
                day(18, "11:07"), "closed_end.other_rate", "Lead with the APR; drop the note rate in 90 characters."
            ),
            Decide(
                day(18, "11:15"),
                O.CHANGES_REQUESTED,
                "Don't call the ARM rate fixed, say the rate may increase, and lead with the APR.",
            ),
            Resubmit(day(16, "10:00"), 1, "Rewrote around the APR with the increase statement."),
            Claim(day(15, "09:10")),
            Checklist(day(15, "09:15")),
            Decide(day(15, "09:20"), O.APPROVED, "APR led, increase statement present, no fixed claim."),
            Place(day(15, "14:00"), "Google Ads: mortgage ARM ad group", first_run=-14),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="mtg-homebound-script",
        owner="jordan",
        title="HomeBound Leads: warm-transfer script (CA)",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.CALL_SCRIPT,
        partner="homebound",
        markets=CA,
        tags=("lead-gen", "california"),
        first_run=5,
        versions=(
            "[HomeBound agent] Thanks for waiting. I'm connecting you with ClearPath Home Lending, who pays "
            "HomeBound for referrals like this one.\n\n"
            "[ClearPath loan officer] Hi, this is [name] with ClearPath Home Lending. HomeBound mentioned you're "
            "shopping for a home in the Sacramento area. Get pre-approved in minutes and make an offer this weekend; "
            "I'll just need a few details about your income and savings.\n\n"
            f"{CRMLA_LINE}",
        ),
        steps=(
            Submit(day(2, "13:45")),
            Claim(day(1, "11:20")),
            Accept(day(1, "11:30"), "mortgage.preapproval_offer", 'We offer prequalification; use "get prequalified".'),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="mtg-homebound-lp",
        owner="jordan",
        title="HomeBound Leads: co-branded prequal page (CA)",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.LANDING_PAGE,
        partner="homebound",
        markets=CA,
        tags=("lead-gen", "california"),
        first_run=4,
        versions=(
            "HomeBound + ClearPath Home Lending\n\n"
            "Paid partnership: HomeBound Leads is compensated by ClearPath for referrals.\n\n"
            "Buying in California? See how much you could borrow in about 10 minutes. "
            f"{NOT_AN_APPROVAL}\n\n"
            "Get prequalified\n\n"
            f"{CRMLA_LINE}",
        ),
        steps=(
            Submit(day(4, "10:10")),
            Claim(day(3, "09:30")),
            Dismiss(day(3, "09:38"), "ca.license_disclosure", CRMLA_DISMISSAL),
            Checklist(day(3, "09:42")),
            Decide(
                day(3, "09:50"),
                O.APPROVED,
                "Partner disclosure up top, prequal described accurately, CRMLA line present. Approved; HomeBound "
                "goes live next week.",
            ),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="mtg-email-rates-dropped",
        owner="elena",
        title="Email: refi rates just dropped",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.EMAIL,
        tags=("refinance", "email"),
        first_run=4,
        last_run=11,
        versions=(
            "Subject: Mortgage rates just dropped\n\n"
            "Cut your monthly payment by $412 when you refinance with ClearPath. Rates from 6.250% (6.471% APR) on a "
            "30-year fixed.\n\n"
            "Get prequalified\n\n"
            f"{EMAIL_FOOTER}",
        ),
        steps=(
            Submit(
                day(7, "14:40"),
                AiResult(
                    (
                        AiFinding(
                            "llm.mortgage_comparison",
                            "Cut your monthly payment by $412",
                            "This payment comparison may need the rates and payments that apply over the full loan "
                            "term, and the loan it's compared against.",
                            "See what your payment could be.",
                        ),
                    )
                ),
            ),
            Claim(day(6, "10:10")),
            Accept(day(6, "10:14"), "llm.mortgage_comparison", "Agree; we can't support $412 for every reader."),
            Accept(day(6, "10:15"), "pricing.as_low_as_range"),
            Accept(day(6, "10:16"), "closed_end.trigger_repayment"),
            Accept(day(6, "10:17"), "closed_end.trigger_downpayment", "State the down payment the rate assumes."),
            Decide(
                day(6, "10:30"),
                O.CHANGES_REQUESTED,
                "Drop the $412 savings claim (it isn't true for every reader), and if you quote a rate, give the full "
                "terms: payment, number of payments and the down payment it assumes.",
            ),
        ),
        expect=ItemStatus.CHANGES_REQUESTED,
    ),
    Story(
        key="mtg-social-first-time",
        owner="elena",
        title="Paid social: first home, first steps",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.PAID_SOCIAL,
        tags=("purchase", "meta"),
        first_run=9,
        versions=(
            "Your first home starts with one number.\n\n"
            "Built for first-time buyers in their 20s and 30s: get prequalified in about 10 minutes and see what you "
            f"could afford. {NOT_AN_APPROVAL}",
        ),
        steps=(
            Submit(
                day(2, "16:20"),
                AiResult(
                    (
                        AiFinding(
                            "llm.discouraging_statement",
                            "Built for first-time buyers in their 20s and 30s",
                            "Naming an age range may discourage older applicants (age is a prohibited basis).",
                            "Built for first-time buyers.",
                        ),
                    )
                ),
            ),
        ),
        expect=ItemStatus.SUBMITTED,
    ),
    Story(
        key="mtg-social-spring",
        owner="elena",
        title="Paid social: prequalify before you shop",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.PAID_SOCIAL,
        tags=("purchase", "meta", "evergreen"),
        first_run=-184,
        versions=(
            "Shop with a number in mind.\n\n"
            "Get prequalified with ClearPath Home Lending in about 10 minutes, then tour homes knowing your budget. "
            f"{NOT_AN_APPROVAL}",
        ),
        steps=(
            Submit(day(188, "10:00")),
            Claim(day(187, "09:30")),
            Checklist(day(187, "09:40")),
            Decide(day(187, "09:45"), O.APPROVED, "No terms quoted; prequal described accurately."),
            Place(day(186, "09:00"), "Meta: mortgage evergreen prospecting", first_run=-184),
            EditFields(day(186, "09:30"), notes="Evergreen; Elena refreshes creative quarterly."),
            Reaffirm(day(1, "10:05"), "Six-month review: copy unchanged and still running.", finds_new=True),
            Dismiss(
                day(1, "10:12"),
                "human.reg_b_discouragement",
                "New since the April approval: the Reg B 1002.4(b) rewrite took effect 7/21. Re-checked the current "
                "creative and Meta audience settings; broad targeting, no exclusions.",
            ),
            Reaffirm(day(1, "10:15"), "Six-month review: copy unchanged, still accurate under the current rules."),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="mtg-direct-mail-preapproved",
        owner="elena",
        title="Direct mail: homeowners refi postcard",
        product=P.MORTGAGE_PREQUAL,
        channel=Channel.DIRECT_MAIL,
        tags=("refinance",),
        first_run=14,
        versions=(
            "Homeowner, you're pre-approved to lower your payment.\n\n"
            "ClearPath Home Lending can help you refinance into a lower monthly payment of $1,890/month on a "
            "30-year term. Call 1-800-555-0142.\n\n"
            f"{ADDRESS}",
        ),
        steps=(
            Submit(day(3, "11:05")),
            EditFields(day(3, "11:40"), by="rachel", notes="Elena asked for a quick turn; mail house deadline Friday."),
            Claim(day(2, "09:05")),
            Accept(day(2, "09:12"), "claims.preapproved", "Not a prescreened list; it can't say pre-approved."),
            Comment(
                day(2, "09:20"),
                "Also needs the APR and full repayment terms with that payment. @Elena Ruiz is this list from the "
                "servicing file or purchased?",
                mentions=("elena",),
            ),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
)
