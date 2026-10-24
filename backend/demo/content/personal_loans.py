"""Personal loan items. The PL floor was 9.49% until six days before the seed, 9.99% since (people.TERMS)."""

from typing import Final

from core.domain import AttachmentKind as K
from core.domain import Channel, DriftResult, ItemStatus, Market, ReopenReason
from core.domain import DecisionOutcome as O
from core.domain import Product as P
from demo.content.copy import (
    CFL_LINE,
    EMAIL_FOOTER,
    SOFT_PULL,
    SUBJECT_TO_APPROVAL,
    pl_range,
)
from demo.story import (
    Accept,
    AiFinding,
    AiOutage,
    AiPending,
    AiResult,
    Assign,
    Attach,
    Checklist,
    Claim,
    Comment,
    Decide,
    Dismiss,
    FastTrack,
    OnDemoPage,
    PageCheck,
    PartnerEdit,
    Place,
    Pull,
    Resubmit,
    Story,
    Submit,
    ago,
    day,
)
from drift.demo import DemoPage, get_page


def demo_page(slug: str) -> DemoPage:
    page = get_page(slug)
    if page is None:
        raise LookupError(slug)
    return page


CA: Final = (Market.NATIONAL, Market.CA)

SOFT_PULL_MEMO: Final = (
    "Substantiation: rate check uses a soft inquiry\n\n"
    "Prepared by Credit Risk, reviewed by Compliance.\n"
    "The ClearPath rate-check flow (clearpath.example/check-rate) requests a soft inquiry from TransUnion "
    "(product code SOFT-PQ). Soft inquiries are not visible to other lenders and do not affect credit scores. "
    "A hard inquiry is made only when the applicant accepts an offer and submits a full application.\n"
    "Evidence: TU integration spec v4.2 section 3.1; production request log sample for 2026-09-14 (attached to "
    "the Credit Risk ticket CR-2210)."
)
CONSENT_EXPORT: Final = (
    "SMS consent export: segment PL-RATECHECK-OPTIN\n\n"
    "Source: Braze subscription group 'ClearPath SMS offers'. 18,412 numbers.\n"
    "Each number opted in through the web form with: 'By checking this box I agree to receive recurring marketing "
    "texts from ClearPath Financial at the number provided. Consent is not a condition of purchase. Msg & data "
    "rates may apply. Reply STOP to cancel.' Timestamp, IP and form version are stored per number."
)

PL_STORIES: Final = (
    Story(
        key="pl-consolidation-lp",
        owner="priya",
        title="PL debt consolidation landing page",
        product=P.PERSONAL_LOAN,
        channel=Channel.LANDING_PAGE,
        markets=CA,
        tags=("debt-consolidation", "always-on"),
        first_run=-52,
        versions=(
            "Consolidate high-interest credit card debt into one fixed monthly payment\n\n"
            "Personal loans as low as 9.49% APR. Borrow up to $50,000 and pay it off on your schedule.\n\n"
            "See your rate in 2 minutes. It won't affect your credit score, and funds can arrive as soon as the "
            "next business day.\n\n"
            "Check your rate",
            "Consolidate high-interest credit card debt into one fixed monthly payment\n\n"
            f"{pl_range('9.49')} Borrow $1,000 to $50,000 over 24 to 60 months. Origination fee of 0% to 8% of the "
            "loan amount, deducted from the proceeds.\n\n"
            "Borrow $15,000 at 9.49% APR and make 48 monthly payments of $365.\n\n"
            f"{SOFT_PULL} Funds can arrive as soon as the next business day after approval.\n\n"
            f"{CFL_LINE}",
            "Consolidate high-interest credit card debt into one fixed monthly payment\n\n"
            f"{pl_range('9.49')} Borrow $1,000 to $50,000 over 24 to 60 months. Origination fee of 0% to 8% of the "
            "loan amount, deducted from the proceeds.\n\n"
            "Representative example: a $15,000 loan over 48 months at 9.49% APR has 48 monthly payments of $376.\n\n"
            f"{SOFT_PULL} Funds can arrive as soon as the next business day after approval.\n\n"
            f"{CFL_LINE}",
        ),
        steps=(
            Submit(day(63, "10:12")),
            Claim(day(63, "14:30")),
            Accept(day(63, "14:41"), "pricing.as_low_as_range", "Show the full APR range next to the floor."),
            Accept(day(63, "14:42"), "pricing.creditworthiness_qualifier", "Needs the credit-based pricing line."),
            Accept(day(63, "14:44"), "claims.credit_impact", "Limit the credit-score claim to checking a rate."),
            Accept(day(63, "14:46"), "ca.license_disclosure", "Page takes CA traffic; needs the CFL line."),
            Comment(
                day(63, "14:52"),
                "While you're in here, add the standard representative example; LPs that quote a range carry it.",
            ),
            Decide(
                day(63, "14:58"),
                O.CHANGES_REQUESTED,
                "Four required changes: the full APR range with the credit-based pricing line, the CFL license line "
                "for CA traffic, and the credit-score claim limited to checking a rate. Please also add the standard "
                "representative example.",
            ),
            Resubmit(day(61, "11:20"), 1, "Added the APR range, CFL line and rep example; reworded the credit claim."),
            Claim(day(61, "15:05")),
            Accept(
                day(61, "15:12"),
                "closed_end.example_payment",
                "$15,000 at 9.49% over 48 months is $376 a month, not $365.",
            ),
            Accept(day(61, "15:13"), "closed_end.example_labeled", 'Label it "Representative example".'),
            Accept(
                day(61, "15:14"),
                "claims.credit_impact",
                "Wording is right now; attach the soft-pull memo so the claim is substantiated.",
            ),
            Decide(
                day(61, "15:20"),
                O.CHANGES_REQUESTED,
                'Round 2: the example payment is off ($376, not $365) and needs the "Representative example" label, '
                "and the credit-score line needs the soft-pull substantiation memo attached.",
            ),
            Attach(day(59, "16:00"), K.SUBSTANTIATION, "soft-pull-substantiation-memo.txt", SOFT_PULL_MEMO),
            Resubmit(day(59, "16:05"), 2, "Fixed the example payment; soft-pull memo attached."),
            Claim(day(58, "09:41")),
            Checklist(day(58, "09:50")),
            Decide(
                day(58, "09:55"),
                O.APPROVED,
                "Range, credit qualifier, example and CFL line all match the 6/1 rate sheet. The credit-score claim "
                "is limited to checking a rate and substantiated by the soft-pull memo.",
            ),
            Place(
                day(55, "13:00"),
                "clearpath.example/debt-consolidation (organic and paid traffic)",
                first_run=-52,
                url="https://clearpath.example/debt-consolidation",
            ),
            Assign(day(5, "08:30"), "dana", "Spreading the rate-change re-reviews; Sam has the prescreen audit."),
        ),
        expect=ItemStatus.NEEDS_REREVIEW,
        expect_reason=ReopenReason.TERMS_CHANGED,
    ),
    Story(
        key="pl-search-consolidation",
        owner="priya",
        title="Paid search: debt consolidation ad group",
        product=P.PERSONAL_LOAN,
        channel=Channel.PAID_SEARCH,
        tags=("debt-consolidation",),
        first_run=-45,
        versions=(
            "Debt Consolidation Loans | ClearPath Financial\n"
            "Fixed APRs 9.49%-35.99%. Rates based on credit. Borrow $1,000-$50,000. Check your rate online.",
        ),
        steps=(
            Submit(day(47, "09:15")),
            Claim(day(47, "11:02")),
            Checklist(day(47, "11:08")),
            Decide(
                day(47, "11:10"),
                O.APPROVED,
                "Full range with the credit qualifier; no other trigger terms. Matches the rate sheet.",
            ),
            Place(day(46, "10:00"), "Google Ads: Debt Consolidation (exact and phrase match)", first_run=-45),
            FastTrack(day(5, "10:20"), "Floor updated to 9.99%; nothing else in the ad changed."),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="pl-display-amounts",
        owner="priya",
        title="Display banner: one payment, one plan",
        product=P.PERSONAL_LOAN,
        channel=Channel.DISPLAY,
        tags=("debt-consolidation", "retargeting"),
        first_run=-38,
        versions=(
            "One payment. One plan.\n"
            f"Borrow $1,000 to $50,000 to pay off credit cards. {SUBJECT_TO_APPROVAL}\n"
            "Check your rate at clearpath.example/consolidate",
        ),
        steps=(
            Submit(day(40, "13:40")),
            Claim(day(39, "09:30")),
            Checklist(day(39, "09:36")),
            Decide(day(39, "09:40"), O.APPROVED, "No rate or payment quoted; the amount range matches the rate sheet."),
            Place(day(38, "15:00"), "The Trade Desk retargeting: 300x250 and 728x90", first_run=-38),
            Assign(day(5, "08:35"), "rachel", "Numbers-unchanged confirm after the rate sheet; I'll clear it."),
        ),
        expect=ItemStatus.NEEDS_REREVIEW,
        expect_reason=ReopenReason.TERMS_CHANGED,
    ),
    Story(
        key="pl-prescreen-mail",
        owner="priya",
        title="Prescreened firm-offer letter, fall drop",
        product=P.PERSONAL_LOAN,
        channel=Channel.DIRECT_MAIL,
        markets=CA,
        prescreen=True,
        tags=("prescreen", "fall-drop"),
        first_run=-26,
        last_run=-12,
        versions=(
            "Good news: you've been pre-selected for a ClearPath personal loan of up to $35,000.\n\n"
            "Pay off high-interest cards with one fixed monthly payment. Fixed APRs from 9.49% to 35.99% based on "
            "your credit. This prescreened offer is good until the date on your reply card.\n\n"
            "Go to clearpath.example/offer and enter your invitation code.",
            "You've been pre-selected for a ClearPath personal loan of up to $35,000.\n\n"
            "Pay off high-interest cards with one fixed monthly payment. Fixed APRs from 9.49% to 35.99% based on "
            "your credit; the lowest rates go to the most creditworthy applicants. This offer is good until the date "
            "on your reply card. Go to clearpath.example/offer and enter your invitation code.\n\n"
            'You can choose to stop receiving "prescreened" offers of credit from this and other companies by '
            "calling toll-free 1-888-5-OPT-OUT (1-888-567-8688). See PRESCREEN & OPT-OUT NOTICE below for more "
            "information about prescreened offers.\n\n"
            "PRESCREEN & OPT-OUT NOTICE\n"
            'This "prescreened" offer of credit is based on information in your credit report indicating that you '
            "meet certain criteria. This offer is not guaranteed if you do not meet our criteria, including "
            "providing acceptable property as collateral where applicable, and verification of your income and "
            "identity. If you do not want to receive prescreened offers of credit from this and other companies, "
            "call the consumer reporting agencies toll-free, 1-888-5-OPT-OUT (1-888-567-8688); or write: "
            "Experian, PO Box 919, Allen, TX 75013; TransUnion, PO Box 505, Woodlyn, PA 19094.\n\n"
            f"{CFL_LINE}",
        ),
        steps=(
            Submit(day(36, "10:00")),
            Claim(day(35, "09:04")),
            Accept(day(35, "09:20"), "prescreen.criteria_on_file", "Attach the bureau selection criteria."),
            Accept(day(35, "09:21"), "prescreen.short_notice"),
            Accept(day(35, "09:22"), "prescreen.long_notice"),
            Accept(day(35, "09:24"), "claims.preapproved", "Fine once the criteria are on file."),
            Comment(
                day(35, "09:31"),
                "@Rachel Okafor the bureau criteria memo says 660+ FICO and no bankruptcies in 24 months. Are we OK "
                'printing "pre-selected" once that\'s attached?',
                mentions=("rachel",),
            ),
            Comment(
                day(35, "10:12"),
                "Yes: pre-selected is fine for a true firm offer with the criteria on file. Keep the long notice on "
                "the back at 8pt minimum with its own heading.",
                by="rachel",
            ),
            Decide(
                day(35, "10:30"),
                O.CHANGES_REQUESTED,
                "Firm-offer letter needs both FCRA notices (short notice on the front, PRESCREEN & OPT-OUT NOTICE on "
                "the back) and the selection criteria on file. Also needs the CFL line for the CA part of the list.",
            ),
            Attach(
                day(33, "14:00"),
                K.PRESCREEN_CRITERIA,
                "prescreen-criteria-fall-drop.txt",
                "Prescreen selection criteria, fall PL drop\n\nBureau: TransUnion prescreen file PS-2026-09.\n"
                "Criteria: FICO 8 >= 660; no bankruptcy or foreclosure in 24 months; revolving utilization <= 85%; "
                "no 60+ day delinquency in 12 months; residence in a ClearPath lending state.\n"
                "Firm offer: up to $35,000, APR set within the published range by the full application.",
            ),
            Resubmit(day(33, "14:10"), 1, "Both notices added, criteria file attached, CFL line in the footer."),
            Claim(day(32, "10:40")),
            Dismiss(
                day(32, "10:50"),
                "pricing.terms_current",
                "$35,000 is this segment's firm-offer cap in the criteria file; within the $50,000 rate-sheet maximum.",
            ),
            Checklist(
                day(32, "10:55"),
                notes=(
                    (
                        "human.prescreen_format",
                        "Proof checked: short notice on the front above the fold, long notice on the reverse in "
                        "10pt with its own heading and border.",
                    ),
                ),
            ),
            Decide(
                day(32, "11:00"),
                O.APPROVED,
                "Notices present and laid out per Reg V; criteria on file back the pre-selected language; CFL line "
                "present.",
            ),
            Place(day(30, "09:00"), "USPS drop 1: 48,000 pieces (CA and national list)", first_run=-26, last_run=-12),
        ),
        expect=ItemStatus.EXPIRED,
        expect_reason=ReopenReason.APPROVAL_EXPIRED,
    ),
    Story(
        key="pl-sms-preapproved",
        owner="hannah",
        title="SMS: pre-approved for $25k",
        product=P.PERSONAL_LOAN,
        channel=Channel.SMS,
        tags=("sms",),
        first_run=-27,
        versions=(
            "ClearPath: Good news, Jamie! You're pre-approved for up to $25,000. Rates from 9.49%. "
            "Tap to claim: clearpath.example/s/7Hk2",
        ),
        steps=(
            Submit(day(30, "16:45")),
            Claim(day(29, "09:10")),
            Accept(day(29, "09:18"), "claims.preapproved"),
            Accept(day(29, "09:19"), "closed_end.apr_label"),
            Accept(day(29, "09:20"), "sms.opt_out"),
            Accept(day(29, "09:21"), "sms.consent_record"),
            Decide(
                day(29, "09:40"),
                O.REJECTED,
                "This list isn't prescreened, so \"pre-approved\" can't run, and the purchased-list numbers have no "
                "consent records. Rework it as a check-your-rate text to the opted-in customer segment instead.",
            ),
        ),
        expect=ItemStatus.REJECTED,
    ),
    Story(
        key="pl-sms-ratecheck",
        owner="hannah",
        title="SMS: check your rate reminder",
        product=P.PERSONAL_LOAN,
        channel=Channel.SMS,
        tags=("sms", "lifecycle"),
        first_run=-25,
        last_run=-20,
        versions=(
            "ClearPath: Still carrying a balance on your cards? See if a fixed-rate personal loan could lower what "
            "you pay. Checking your rate won't affect your credit score. clearpath.example/r/8XK2 "
            "Reply STOP to opt out.",
        ),
        steps=(
            Submit(day(28, "10:30")),
            Attach(day(28, "10:32"), K.CONSENT_RECORD, "braze-sms-consent-export.txt", CONSENT_EXPORT),
            Attach(day(28, "10:33"), K.SUBSTANTIATION, "soft-pull-substantiation-memo.txt", SOFT_PULL_MEMO),
            Claim(day(27, "09:20")),
            Checklist(
                day(27, "09:28"),
                notes=(("human.sms_send_window", "Braze sends 10:00-18:00 recipient local time; inside 8am-9pm."),),
            ),
            Decide(
                day(27, "09:35"),
                O.APPROVED,
                "Consent export matches the segment; STOP language present; the credit claim is limited to checking "
                "a rate and substantiated. Approved for the planned send window.",
            ),
            Place(day(25, "10:00"), "Braze: PL rate-check reminder, weekly cadence", first_run=-25, last_run=3),
            Comment(
                day(18, "11:05"),
                "Braze shows this cadence still sending; the approval covered the original five-day window. Hannah, "
                "can you confirm the consent export is still current before I reaffirm?",
            ),
        ),
        expect=ItemStatus.NEEDS_REREVIEW,
        expect_reason=ReopenReason.APPROVAL_EXPIRED,
    ),
    Story(
        key="pl-email-rate-lower",
        owner="hannah",
        title="Email: your rate could be lower",
        product=P.PERSONAL_LOAN,
        channel=Channel.EMAIL,
        tags=("lifecycle", "email"),
        first_run=-10,
        last_run=4,
        versions=(
            "Subject: RE: your personal loan rate\n"
            "Preheader: Rates as low as 9.49% APR for people like you\n\n"
            "Hi Sam,\n\n"
            "Rates have moved. ClearPath personal loans start as low as 9.49% APR, and you can check yours in two "
            "minutes.\n\n"
            "Check my rate",
            "Subject: Your personal loan rate could be lower\n"
            "Preheader: Check your rate in two minutes\n\n"
            "Hi Sam,\n\n"
            f"Rates have moved. {pl_range('9.49')} Borrow $1,000 to $50,000. {SUBJECT_TO_APPROVAL}\n\n"
            "Check my rate\n\n"
            f"{EMAIL_FOOTER}",
        ),
        steps=(
            Submit(day(16, "11:00")),
            Claim(day(15, "10:00")),
            Accept(day(15, "10:05"), "email.subject_reply_prefix"),
            Accept(day(15, "10:06"), "email.opt_out"),
            Accept(day(15, "10:06"), "email.postal_address"),
            Accept(day(15, "10:07"), "email.ad_identification"),
            Accept(day(15, "10:09"), "pricing.as_low_as_range"),
            Accept(day(15, "10:10"), "pricing.creditworthiness_qualifier"),
            Decide(
                day(15, "10:18"),
                O.CHANGES_REQUESTED,
                'The standard CAN-SPAM footer is missing (ad label, unsubscribe, postal address), and drop "RE:" '
                "from the subject; it implies a reply. Show the full APR range with the credit line.",
            ),
            Resubmit(day(14, "15:30"), 1, "Footer added, subject fixed, full range in."),
            Claim(day(13, "10:02")),
            Checklist(day(13, "10:10")),
            Decide(day(13, "10:15"), O.APPROVED, "Footer complete; range and qualifier match the rate sheet."),
            Place(day(12, "09:00"), "Braze: PL lifecycle, three-send series", first_run=-10, last_run=4),
            FastTrack(day(5, "14:02"), "Rate sheet update only; remaining sends go out with 9.99%."),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="pl-lendcompare-listing",
        owner="jordan",
        title="LendCompare: best debt consolidation loans listing",
        product=P.PERSONAL_LOAN,
        channel=Channel.AFFILIATE_PAGE,
        partner="lendcompare",
        tags=("affiliate", "debt-consolidation"),
        first_run=-39,
        versions=(
            "Best Debt Consolidation Loans This Year\n\n"
            "ClearPath Financial: Editor's Pick\n"
            "Rates as low as 9.49% APR. Loans up to $50,000. Guaranteed approval for most applicants with fair "
            "credit or better.\n\n"
            "Why we like it: fast funding, no prepayment penalty, and a simple online application.\n\n"
            "See my rates",
            # As approved in round 2, before the rate sheet: the fast-track to 9.99% makes it the demo page's copy.
            demo_page("lendcompare").copy.replace("9.99%", "9.49%"),
        ),
        steps=(
            Submit(day(44, "09:00")),
            Claim(day(43, "10:15")),
            Accept(day(43, "10:20"), "endorsement.material_connection", "Advertiser disclosure above the listings."),
            Accept(day(43, "10:21"), "claims.guaranteed"),
            Accept(day(43, "10:22"), "pricing.as_low_as_range"),
            Accept(day(43, "10:23"), "pricing.creditworthiness_qualifier"),
            Decide(
                day(43, "10:30"),
                O.CHANGES_REQUESTED,
                "Partner page: needs LendCompare's advertiser disclosure above the listings, and approval can't be "
                "guaranteed. Use the full APR range from our rate feed.",
            ),
            Resubmit(day(41, "13:00"), 1, "LendCompare added their standard disclosure and pulled the guarantee."),
            Claim(day(40, "09:45")),
            Checklist(day(40, "09:55")),
            Decide(day(40, "10:00"), O.APPROVED, "Disclosure at the top, range and qualifier current, no guarantee."),
            OnDemoPage(day(39, "12:00"), "lendcompare"),
            FastTrack(day(5, "11:40"), "Floor to 9.99%; LendCompare's feed picks it up tonight."),
            PageCheck(day(4, "06:20"), DriftResult.UNCHANGED),
            PartnerEdit(day(2, "05:10")),
            PageCheck(day(2, "06:20"), DriftResult.MODIFIED),
            Assign(
                day(2, "08:50"), "dana", "Live partner page with drift; Dana is covering partner content this week."
            ),
            Comment(
                day(2, "09:12"),
                "This morning's check: LendCompare's listing now starts our APRs at 7.99% and says \"Guaranteed "
                'approval for most applicants" instead of "Subject to credit approval." That\'s the guarantee we '
                "took out in round 1. @Jordan Whitfield can you get them back to the approved copy today?",
                mentions=("jordan",),
            ),
        ),
        expect=ItemStatus.NEEDS_REREVIEW,
        expect_reason=ReopenReason.DRIFT_DETECTED,
    ),
    Story(
        key="pl-rateradar-listing",
        owner="jordan",
        title="RateRadar: ClearPath lender profile",
        product=P.PERSONAL_LOAN,
        channel=Channel.AFFILIATE_PAGE,
        partner="rateradar",
        tags=("affiliate",),
        first_run=-32,
        last_run=-9,
        versions=(
            "Sponsored listing. RateRadar is compensated by lenders on this page.\n\n"
            "ClearPath Financial Personal Loans\n"
            f"{pl_range('9.49')} Amounts from $1,000 to $50,000. Terms from 24 to 60 months. Origination fee 0% to "
            "8%.\n\n"
            "Representative example: a $10,000 loan over 36 months at 9.49% APR has 36 monthly payments of $320.\n\n"
            "Check your rate on ClearPath's site",
        ),
        steps=(
            Submit(day(34, "14:20")),
            Claim(day(33, "09:12")),
            Checklist(day(33, "09:25")),
            Decide(day(33, "09:30"), O.APPROVED, "Disclosure first, rate-sheet numbers, example computes."),
            Place(
                day(32, "11:00"),
                "RateRadar: lenders/clearpath-financial (weekly feed)",
                first_run=-32,
                last_run=-9,
                url="https://rateradar.example/lenders/clearpath-financial",
            ),
        ),
        expect=ItemStatus.EXPIRED,
        expect_reason=ReopenReason.TERMS_CHANGED,
    ),
    Story(
        key="pl-social-breathe",
        owner="priya",
        title="Paid social: consolidate and breathe",
        product=P.PERSONAL_LOAN,
        channel=Channel.PAID_SOCIAL,
        tags=("debt-consolidation", "meta"),
        first_run=-33,
        last_run=-10,
        versions=(
            "Five card payments. Five due dates. Breathe.\n\n"
            "Roll them into one fixed-rate ClearPath personal loan. Fixed APRs 9.49% to 35.99% based on your "
            "credit. Rates this low won't last; check yours today.",
            "Five card payments. Five due dates. Breathe.\n\n"
            "Roll them into one fixed-rate ClearPath personal loan. Fixed APRs 9.49% to 35.99% based on your "
            "credit. Check your rate in two minutes.",
        ),
        steps=(
            Submit(
                day(37, "15:10"),
                AiResult(
                    (
                        AiFinding(
                            "llm.pressure_tactics",
                            "Rates this low won't last",
                            "Rates this low won't last: confirm a real deadline exists, or remove the urgency.",
                            "Check your rate in two minutes.",
                        ),
                    )
                ),
            ),
            Claim(day(36, "10:30")),
            Accept(day(36, "10:34"), "llm.pressure_tactics", "Agree; no deadline on the rate sheet."),
            Decide(day(36, "10:40"), O.CHANGES_REQUESTED, 'Drop the "won\'t last" urgency; we have no rate deadline.'),
            Resubmit(day(35, "09:15"), 1, "Swapped the urgency line for the rate-check CTA."),
            Claim(day(35, "13:20")),
            Checklist(day(35, "13:25")),
            Decide(day(35, "13:30"), O.APPROVED, "Clean: range, credit qualifier, neutral CTA."),
            Place(day(34, "09:00"), "Meta: PL consolidation, feed and stories", first_run=-33, last_run=-10),
        ),
        expect=ItemStatus.EXPIRED,
        expect_reason=ReopenReason.TERMS_CHANGED,
    ),
    Story(
        key="pl-maya-reel",
        owner="jordan",
        title="Money with Maya: card payoff reel",
        product=P.PERSONAL_LOAN,
        channel=Channel.PAID_SOCIAL,
        partner="maya",
        tags=("influencer",),
        first_run=3,
        versions=(
            "#collab Real talk: I paid off $11k of card debt with a @ClearPath personal loan and my payments finally "
            "make sense. No credit check to see your rate, so there's zero reason not to look. Link in bio!",
            "#ad Paid partnership with ClearPath\n\n"
            "Real talk: I paid off $11k of card debt with a @ClearPath personal loan and my payments finally make "
            "sense. Checking your rate takes two minutes. Rates this low won't last, so go look before they're gone! "
            "Link in bio.",
        ),
        steps=(
            Submit(day(10, "17:30")),
            Claim(day(9, "09:50")),
            Accept(day(9, "09:55"), "endorsement.material_connection", '"#collab" isn\'t a disclosure; use #ad.'),
            Accept(day(9, "09:56"), "claims.credit_impact", "A soft pull is still a credit check."),
            Decide(
                day(9, "10:05"),
                O.CHANGES_REQUESTED,
                'Maya\'s agreement requires "#ad" or "Paid partnership with ClearPath" in the first line, and '
                '"no credit check" isn\'t accurate: checking a rate is a soft inquiry.',
            ),
            Resubmit(
                day(6, "18:10"),
                1,
                "Maya's revised caption.",
                AiResult(
                    (
                        AiFinding(
                            "llm.pressure_tactics",
                            "Rates this low won't last, so go look before they're gone!",
                            "This urgency line implies rates are about to rise; confirm a real deadline or remove it.",
                            # Replaces the urgency line without repeating the sentence before it (walkthrough S12).
                            "See your rate whenever you're ready.",
                        ),
                    )
                ),
            ),
            Assign(day(5, "08:40"), "dana", "Dana has Maya's last two posts; keeping it with her."),
            Claim(day(5, "09:05"), by="dana"),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="pl-leadstream-email",
        owner="jordan",
        title="LeadStream Direct: debt payoff email",
        product=P.PERSONAL_LOAN,
        channel=Channel.EMAIL,
        partner="leadstream",
        tags=("lead-gen", "email"),
        first_run=2,
        last_run=9,
        versions=(
            "Subject: You've qualified for a lower-rate loan\n\n"
            "Sponsored by ClearPath Financial. LeadStream Direct is paid for this message.\n\n"
            "You've qualified to see personal loan offers from ClearPath. Get cash in minutes and pay off your "
            f"cards with one fixed payment. {pl_range('9.99')}\n\n"
            "See my offer\n\n"
            "This is an advertisement. To unsubscribe from LeadStream Direct emails, click here.",
        ),
        steps=(
            Submit(
                day(3, "15:20"),
                AiResult(
                    (
                        AiFinding(
                            "llm.net_impression",
                            "Get cash in minutes",
                            "Get cash in minutes may overstate funding speed; funds arrive the next business day "
                            "at the earliest.",
                            "Get your rate in minutes.",
                        ),
                    )
                ),
            ),
            Claim(day(2, "10:00")),
            Accept(day(2, "10:08"), "claims.preapproved", '"You\'ve qualified" reads as an approval.'),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="pl-call-script",
        owner="priya",
        title="Inbound call script: personal loan rate check",
        product=P.PERSONAL_LOAN,
        channel=Channel.CALL_SCRIPT,
        tags=("call-center",),
        first_run=-22,
        versions=(
            "Thanks for calling ClearPath, this is [agent name]. Are you calling about a personal loan?\n\n"
            "Great. I can help you check your rate online while we're on the phone; it takes about two minutes. "
            "For existing customers, approval is guaranteed, so you can plan around it.\n\n"
            "Once you see your offers, you can pick the amount and term that work for you, and if you accept, "
            "funds can arrive as soon as the next business day.",
            "Thanks for calling ClearPath, this is [agent name]. Are you calling about a personal loan?\n\n"
            "Great. I can help you check your rate online while we're on the phone; it takes about two minutes. "
            "Any loan is subject to credit approval, including for existing customers.\n\n"
            "Once you see your offers, you can pick the amount and term that work for you, and if you accept, "
            "funds can arrive as soon as the next business day.",
        ),
        steps=(
            Submit(day(24, "11:45")),
            Claim(day(23, "13:30")),
            Accept(day(23, "13:41"), "claims.guaranteed", "Replace with subject-to-approval; I'll make the edit."),
            Checklist(day(23, "13:50")),
            Decide(
                day(23, "14:00"),
                O.APPROVED_WITH_EDITS,
                "One-line fix made directly: removed the approval guarantee for existing customers. The rest of the "
                "script is accurate.",
                edited=1,
            ),
            Place(day(22, "08:30"), "Call center knowledge base article KB-2291 (inbound PL)", first_run=-22),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="pl-goldenstate-review",
        owner="jordan",
        title="Golden State Saver: ClearPath loan review (CA)",
        product=P.PERSONAL_LOAN,
        channel=Channel.AFFILIATE_PAGE,
        partner="goldenstate",
        markets=CA,
        tags=("affiliate", "california"),
        first_run=7,
        versions=(
            "Disclosure: Golden State Saver earns a commission if you're approved through our links.\n\n"
            "ClearPath Personal Loan Review for Californians\n\n"
            "ClearPath offers personal loans as low as 9.49% APR, with your rate based on your credit. You can "
            "borrow $1,000 to $50,000 for debt consolidation, a home project or a big purchase.\n\n"
            "Our take: a solid pick for Bay Area borrowers with good credit who want one fixed payment.",
        ),
        steps=(
            Submit(day(8, "10:25")),
            Claim(day(7, "15:30")),
            Accept(day(7, "15:40"), "ca.license_disclosure", "CA-targeted page; needs our CFL license line."),
            Accept(day(7, "15:41"), "pricing.as_low_as_range"),
            Decide(
                day(7, "16:00"),
                O.CHANGES_REQUESTED,
                "California page needs the CFL license line, and the lowest rate needs the full range next to it.",
            ),
            Comment(
                day(5, "11:30"),
                "Heads up @Jordan Whitfield: the PL floor moved to 9.99% this week, so use the new rate sheet when "
                "Golden State resubmits.",
                mentions=("jordan",),
            ),
        ),
        expect=ItemStatus.CHANGES_REQUESTED,
    ),
    Story(
        key="pl-email-home-projects",
        owner="hannah",
        title="Email: fund your home project",
        product=P.PERSONAL_LOAN,
        channel=Channel.EMAIL,
        tags=("lifecycle", "email", "home-improvement"),
        first_run=6,
        last_run=13,
        versions=(
            "Subject: That kitchen isn't going to remodel itself\n"
            "Preheader: Fixed-rate home improvement loans from ClearPath\n\n"
            "Excellent credit? Not required for our lowest rate. Get a fixed-rate personal loan from $1,000 to "
            f"$50,000 for the project you've been putting off. {pl_range('9.99')}\n\n"
            "Check my rate\n\n"
            f"{EMAIL_FOOTER}",
        ),
        steps=(
            Submit(
                day(4, "14:05"),
                AiResult(
                    (
                        AiFinding(
                            "llm.creditworthiness_qualifier",
                            "Excellent credit? Not required for our lowest rate.",
                            "This line may contradict the credit-based pricing statement below it; the lowest rates "
                            "go to the most creditworthy applicants.",
                            "Remove the line.",
                        ),
                    )
                ),
            ),
            Assign(day(4, "14:30"), "leah", "Leah has the home-improvement campaign."),
        ),
        expect=ItemStatus.SUBMITTED,
    ),
    Story(
        key="pl-display-holiday",
        owner="priya",
        title="Display banner: get ahead of holiday bills",
        product=P.PERSONAL_LOAN,
        channel=Channel.DISPLAY,
        tags=("seasonal",),
        first_run=10,
        versions=(
            "Get ahead of holiday bills.\n"
            f"One fixed monthly payment. {pl_range('9.99')} Borrow $1,000 to $50,000. {SUBJECT_TO_APPROVAL}\n"
            "Check your rate at clearpath.example/holiday",
        ),
        steps=(Submit(ago(4), AiPending()),),
        expect=ItemStatus.SUBMITTED,
    ),
    Story(
        key="pl-finmatch-listing",
        owner="jordan",
        title="FinMatch: prequal marketplace listing",
        product=P.PERSONAL_LOAN,
        channel=Channel.AFFILIATE_PAGE,
        partner="finmatch",
        tags=("affiliate",),
        first_run=5,
        versions=(
            "Advertiser disclosure: FinMatch is compensated by the lenders it shows you.\n\n"
            "ClearPath Financial\n"
            f"{pl_range('9.99')} Loan amounts $1,000 to $50,000. Terms 24 to 60 months.\n\n"
            "See your matched offers with no impact to your credit score. Final approval requires a full "
            "application and a hard credit inquiry.",
        ),
        steps=(
            Submit(day(2, "11:00"), AiOutage()),
            Assign(day(2, "11:40"), "dana", "FinMatch is one of Dana's partners."),
            Claim(day(1, "09:30")),
            Comment(
                day(1, "09:44"),
                "AI check failed during yesterday's provider outage. The credit-score line is FinMatch's own soft-pull "
                "flow; asking Jordan for their substantiation before I decide.",
            ),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="pl-search-california",
        owner="priya",
        title="Paid search: California personal loans",
        product=P.PERSONAL_LOAN,
        channel=Channel.PAID_SEARCH,
        markets=CA,
        tags=("california",),
        first_run=4,
        versions=(
            "California Personal Loans | ClearPath\n"
            "Fixed APRs 9.49%-35.99% based on credit. Apply in minutes with zero impact on your score. "
            f"{CFL_LINE}",
        ),
        steps=(
            Submit(
                day(3, "09:40"),
                AiResult(
                    (
                        AiFinding(
                            "llm.credit_inquiry_scope",
                            "Apply in minutes with zero impact on your score",
                            "Applying involves a hard inquiry; this score claim may need to be limited to checking a "
                            "rate.",
                            "Check your rate in minutes; it won't affect your credit score.",
                        ),
                    )
                ),
            ),
            Claim(day(3, "13:15")),
            Accept(day(3, "13:22"), "pricing.terms_available", "Floor is 9.99% since the rate sheet update."),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="pl-email-new-floor",
        owner="hannah",
        title="Email: new rates for returning customers",
        product=P.PERSONAL_LOAN,
        channel=Channel.EMAIL,
        tags=("lifecycle", "email"),
        first_run=3,
        last_run=10,
        versions=(
            "Subject: Welcome back. Here's what's new at ClearPath\n"
            "Preheader: Check your rate in two minutes\n\n"
            f"It's been a while. If you're thinking about consolidating, {pl_range('9.99')} Borrow $1,000 to "
            f"$50,000. {SUBJECT_TO_APPROVAL}\n\n"
            "Check my rate\n\n"
            f"{EMAIL_FOOTER}",
        ),
        steps=(Submit(day(1, "13:00")),),
        expect=ItemStatus.SUBMITTED,
    ),
    Story(
        key="pl-social-video",
        owner="priya",
        title="Paid social video: one payment, 15s",
        product=P.PERSONAL_LOAN,
        channel=Channel.PAID_SOCIAL,
        tags=("debt-consolidation", "video"),
        first_run=-28,
        versions=(
            "[VO] Five cards, five due dates. Or one fixed payment.\n"
            "[Super] ClearPath personal loans. Fixed APRs 9.49% to 35.99% based on your credit. Subject to credit "
            "approval.\n"
            "[End card] Check your rate at clearpath.example",
        ),
        steps=(
            Submit(day(31, "16:00")),
            Claim(day(30, "11:10")),
            Checklist(day(30, "11:20")),
            Decide(day(30, "11:25"), O.APPROVED, "Super carries the range and qualifier for the full 15 seconds."),
            Place(day(29, "09:00"), "TikTok and Meta Reels: PL awareness flight", first_run=-28),
            Pull(day(4, "10:40"), "Flight ends this week; pausing rather than re-cutting the super for 9.99%."),
        ),
        expect=ItemStatus.WITHDRAWN,
    ),
    Story(
        key="pl-budgetbee-article",
        owner="jordan",
        title="BudgetBee: debt consolidation article",
        product=P.PERSONAL_LOAN,
        channel=Channel.AFFILIATE_PAGE,
        partner="budgetbee",
        tags=("affiliate", "sponsored", "debt-consolidation"),
        first_run=-3,
        versions=(demo_page("budgetbee").copy,),
        steps=(
            Submit(day(5, "10:20")),
            Claim(day(4, "09:30")),
            Checklist(day(4, "09:40")),
            Decide(
                day(4, "09:50"),
                O.APPROVED,
                "Sponsored label and fee disclosure up top, today's 9.99% floor and range, CFL line. BudgetBee runs "
                "it word for word; their page is on the drift monitor.",
            ),
            OnDemoPage(day(3, "08:00"), "budgetbee"),
            PageCheck(day(2, "06:20"), DriftResult.UNCHANGED),
        ),
        expect=ItemStatus.APPROVED,
    ),
)
