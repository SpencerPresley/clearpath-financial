"""ClearPath Card items. Purchase APRs were 24.99%-33.99% until twenty days before the seed, 24.74%-33.74% since."""

from typing import Final

from core.domain import AttachmentKind as K
from core.domain import Channel, ItemStatus
from core.domain import DecisionOutcome as O
from core.domain import Product as P
from demo.content.copy import EMAIL_FOOTER, ISSUER_LINE, card_terms
from demo.story import (
    Accept,
    AiFinding,
    AiResult,
    Assign,
    Attach,
    Checklist,
    Claim,
    Comment,
    ConfirmTakedown,
    Decide,
    Dismiss,
    FastTrack,
    NewRound,
    Place,
    Pull,
    Resubmit,
    Story,
    Submit,
    day,
)

OLD: Final = card_terms("24.99", "33.99")
NEW: Final = card_terms("24.74", "33.74")

PROGRAM_LETTER: Final = (
    "Harborview Bank, N.A. / ClearPath Card program: launch offer confirmation\n\n"
    "Harborview approves the ClearPath Card launch offer: 0% intro APR on purchases for 15 months from account "
    "opening for accounts opened through the launch landing page. Harborview marketing review ref HBV-MKT-0912. "
    "Sponsor-bank sign-off on card creative is tracked in Harborview's portal."
)

CC_STORIES: Final = (
    Story(
        key="cc-launch-lp",
        owner="marcus",
        title="ClearPath Card launch landing page",
        product=P.CREDIT_CARD,
        channel=Channel.LANDING_PAGE,
        tags=("card-launch",),
        first_run=-48,
        versions=(
            "The ClearPath Card\n\n"
            "Pay down what you owe, without paying more to do it.\n\n"
            f"{OLD}\n\n"
            "Apply by the end of the launch window to get the launch offer. Check if you're "
            "prequalified in about a minute.\n\n"
            f"{ISSUER_LINE}",
        ),
        steps=(
            Submit(
                day(52, "10:00"),
                AiResult(
                    (
                        AiFinding(
                            "llm.pressure_tactics",
                            "Apply by the end of the launch window",
                            "Confirm the launch window is a real, dated offer, or remove the deadline.",
                            "Apply today and start with 15 months at 0% on purchases.",
                        ),
                    )
                ),
            ),
            Attach(day(52, "10:03"), K.SUBSTANTIATION, "harborview-launch-offer-letter.txt", PROGRAM_LETTER),
            Claim(day(51, "09:00")),
            Dismiss(
                day(51, "09:20"),
                "llm.pressure_tactics",
                "Real program window: Harborview's launch offer letter (attached) confirms the launch-page offer.",
            ),
            Checklist(day(51, "09:24")),
            Decide(
                day(51, "09:30"),
                O.APPROVED,
                "Intro APR labeled with its length and the go-to variable range; issuer line present; launch window "
                "backed by Harborview's letter.",
            ),
            Place(
                day(49, "08:00"),
                "clearpath.example/card (launch page)",
                first_run=-48,
                url="https://clearpath.example/card",
            ),
            FastTrack(day(19, "10:15"), "Variable APRs moved with Prime; copy otherwise unchanged."),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="cc-display-no-fee",
        owner="marcus",
        title="Card display: $0 annual fee",
        product=P.CREDIT_CARD,
        channel=Channel.DISPLAY,
        tags=("card-launch",),
        first_run=-42,
        versions=(f"No annual fee. Ever so slightly smarter.\nThe ClearPath Card. {OLD}\n{ISSUER_LINE}",),
        steps=(
            Submit(day(45, "13:20")),
            Claim(day(44, "10:10")),
            Checklist(day(44, "10:18")),
            Decide(day(44, "10:20"), O.APPROVED, "All triggered card disclosures present; issuer line on the frame."),
            Place(day(43, "09:00"), "Google Display Network: card launch prospecting", first_run=-42),
            FastTrack(day(18, "15:40"), "Prime move only."),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="cc-email-balance-transfer",
        owner="hannah",
        title="Email: balance transfer offer",
        product=P.CREDIT_CARD,
        channel=Channel.EMAIL,
        tags=("lifecycle", "email", "balance-transfer"),
        first_run=5,
        last_run=19,
        versions=(
            "Subject: RE: Your ClearPath Card offer\n\n"
            "Make the switch. Transfer your balance and pay 0% APR for 15 months!\n"
            "No interest on purchases for 6 months if paid in full. No annual fee.\n\n"
            "After that, a 24.74% to 33.74% APR applies.\n\n"
            "Apply today at clearpath.example/card.",
            "Subject: Move your balance, keep your plan\n\n"
            "Make the switch to the ClearPath Card.\n\n"
            f"{NEW}\n\n"
            "Apply today at clearpath.example/card.\n\n"
            "Unsubscribe or manage your email preferences at clearpath.example/prefs.\n"
            "ClearPath Financial, Inc., 500 Market Street, Suite 1200, San Francisco, CA 94105",
            "Subject: Move your balance, keep your plan\n\n"
            "Make the switch to the ClearPath Card.\n\n"
            f"{NEW}\n\n"
            "Apply today at clearpath.example/card.\n\n"
            f"{ISSUER_LINE}\n\n"
            f"{EMAIL_FOOTER}",
        ),
        steps=(
            Submit(day(12, "11:30")),
            Claim(day(11, "09:40")),
            Accept(day(11, "09:45"), "email.subject_reply_prefix"),
            Accept(day(11, "09:46"), "card.intro_label", 'Say "intro APR" and what it applies to.'),
            Accept(day(11, "09:47"), "card.intro_terms"),
            Accept(day(11, "09:49"), "card.deferred_interest", "We don't offer deferred interest; remove the line."),
            Accept(day(11, "09:50"), "card.apr_variable"),
            Accept(day(11, "09:51"), "card.trigger_transaction_fees", "State the 3% transfer fee."),
            Accept(day(11, "09:52"), "email.opt_out"),
            Accept(day(11, "09:52"), "email.postal_address"),
            Decide(
                day(11, "10:05"),
                O.CHANGES_REQUESTED,
                "Use the standard card terms block (intro APR labeled with its length, variable APR, transfer fee), "
                'remove the deferred-interest line (we don\'t offer it), drop "RE:" and add the email footer.',
            ),
            Resubmit(day(9, "16:20"), 1, "Swapped in the terms block, removed deferred interest, added a footer."),
            Claim(day(8, "09:15")),
            Accept(day(8, "09:20"), "card.issuer_line", "Card email needs the Harborview issuer line."),
            Accept(day(8, "09:21"), "email.ad_identification", "Use the standard footer; it has the ad label."),
            Decide(
                day(8, "09:30"),
                O.CHANGES_REQUESTED,
                "Close: still needs the Harborview issuer line and the standard footer with the ad label.",
            ),
            Resubmit(day(2, "17:05"), 2, "Issuer line and standard footer added."),
            Claim(day(1, "10:20")),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="cc-social-fixed",
        owner="marcus",
        title="Paid social: one fixed rate",
        product=P.CREDIT_CARD,
        channel=Channel.PAID_SOCIAL,
        tags=("meta",),
        first_run=-20,
        versions=(
            "Meet the ClearPath Card: one fixed 24.99% APR, so your rate never jumps. $0 annual fee. Apply in minutes.",
        ),
        steps=(
            Submit(day(27, "14:00")),
            Claim(day(26, "10:30")),
            Accept(day(26, "10:35"), "card.fixed_apr"),
            Accept(day(26, "10:36"), "card.apr_variable"),
            Comment(
                day(26, "10:50"),
                "@Rachel Okafor rejecting rather than requesting changes: the whole concept is a fixed rate, and the "
                "card's APR is variable. OK with you?",
                mentions=("rachel",),
            ),
            Comment(day(26, "11:05"), "Agreed. Marcus can rework it around the intro offer.", by="rachel"),
            Decide(
                day(26, "11:10"),
                O.REJECTED,
                'The ClearPath Card\'s purchase APR is variable, so "fixed" and "never jumps" can\'t run in any '
                "form, and the concept depends on them. Rework around the intro APR with the standard terms block.",
            ),
        ),
        expect=ItemStatus.REJECTED,
    ),
    Story(
        key="cc-cardperks-review",
        owner="jordan",
        title="CardPerks Weekly: ClearPath Card review",
        product=P.CREDIT_CARD,
        channel=Channel.AFFILIATE_PAGE,
        partner="cardperks",
        tags=("affiliate",),
        first_run=-34,
        versions=(
            "ClearPath Card Review: A Simple Card for Paying Down Balances\n\n"
            "Verdict: 4.5/5. If you're carrying a balance, the 15-month intro period is the headline.\n\n"
            f"{OLD}\n\n"
            "Who it's for: anyone consolidating card debt who wants a no-annual-fee card.\n\n"
            "Some links on this page may earn us a commission.",
            "Advertiser disclosure: CardPerks Weekly earns a commission from ClearPath when readers are approved "
            "through our links.\n\n"
            "ClearPath Card Review: A Simple Card for Paying Down Balances\n\n"
            "Verdict: 4.5/5. If you're carrying a balance, the 15-month intro period is the headline.\n\n"
            f"{OLD}\n\n"
            "Who it's for: anyone consolidating card debt who wants a no-annual-fee card.\n\n"
            f"{ISSUER_LINE}",
        ),
        steps=(
            Submit(
                day(39, "10:00"),
                AiResult(
                    (
                        AiFinding(
                            "llm.material_connection",
                            "Some links on this page may earn us a commission.",
                            "The paid relationship is disclosed only after the review; it may need to sit at the top.",
                            "Advertiser disclosure: CardPerks Weekly earns a commission from ClearPath.",
                        ),
                    )
                ),
            ),
            Claim(day(38, "09:30")),
            Accept(day(38, "09:34"), "llm.material_connection", "Disclosure has to be above the verdict."),
            Accept(day(38, "09:36"), "card.issuer_line"),
            Decide(
                day(38, "09:45"),
                O.CHANGES_REQUESTED,
                "Move the commission disclosure above the review and name ClearPath in it; add the issuer line.",
            ),
            Resubmit(day(37, "12:00"), 1, "CardPerks moved the disclosure up and added the issuer line."),
            Claim(day(36, "10:00")),
            Checklist(day(36, "10:05")),
            Decide(day(36, "10:10"), O.APPROVED, "Disclosure first, standard terms block, issuer line."),
            Place(
                day(35, "16:00"),
                "CardPerks Weekly: reviews/clearpath-cash-back-card",
                first_run=-34,
                url="https://cardperksweekly.example/reviews/clearpath-cash-back-card",
                monitored=True,
            ),
            Comment(
                day(18, "10:00"),
                "CardPerks says they're retiring this review in their site redesign, so they'd rather take it down "
                "than update the APRs. Pulling it.",
                by="jordan",
            ),
            Pull(day(17, "09:30"), "Partner is retiring the page instead of updating it for the new APRs."),
            ConfirmTakedown(day(15, "14:00")),
        ),
        expect=ItemStatus.WITHDRAWN,
    ),
    Story(
        key="cc-prescreen-mail",
        owner="marcus",
        title="Card prescreen mailer: pre-selected offer",
        product=P.CREDIT_CARD,
        channel=Channel.DIRECT_MAIL,
        prescreen=True,
        tags=("prescreen",),
        first_run=12,
        last_run=26,
        versions=(
            "You're pre-selected for the ClearPath Card.\n\n"
            f"{NEW}\n\n"
            "Respond by November 30 to accept this offer. Only a limited number of invitations were mailed.\n\n"
            'You can choose to stop receiving "prescreened" offers of credit from this and other companies by '
            "calling toll-free 1-888-5-OPT-OUT (1-888-567-8688). See PRESCREEN & OPT-OUT NOTICE on the reverse for "
            "more information about prescreened offers.\n\n"
            "PRESCREEN & OPT-OUT NOTICE\n"
            'This "prescreened" offer of credit is based on information in your credit report indicating that you '
            "meet certain criteria. This offer is not guaranteed if you do not meet our criteria, including "
            "verification of your income and identity. If you do not want to receive prescreened offers of credit "
            "from this and other companies, call the consumer reporting agencies toll-free, 1-888-5-OPT-OUT "
            "(1-888-567-8688).\n\n"
            f"{ISSUER_LINE}",
        ),
        steps=(
            Submit(
                day(5, "10:00"),
                AiResult(
                    (
                        AiFinding(
                            "llm.pressure_tactics",
                            "Only a limited number of invitations were mailed.",
                            "Scarcity claim: confirm the mail quantity makes this true, or remove it.",
                            "Remove the line.",
                        ),
                    )
                ),
            ),
            Attach(
                day(5, "10:02"),
                K.PRESCREEN_CRITERIA,
                "card-prescreen-criteria.txt",
                "Card prescreen criteria\n\n"
                "Bureau: Experian prescreen file EX-PS-2611. FICO 8 >= 680; utilization <= 70%; no 90+ day "
                "delinquency in 24 months. Firm offer of the ClearPath Card at the published terms.",
            ),
            Claim(day(4, "09:15")),
            Comment(
                day(4, "09:40"),
                "Notices look right. @Marcus Bell is the November 30 response date the same on the reply card? I'll "
                "need the Harborview sign-off reference too.",
                mentions=("marcus",),
            ),
            Comment(
                day(3, "16:10"),
                "Yes, same date. Harborview ref is HBV-MKT-1031, uploading their email now.",
                by="marcus",
            ),
        ),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="cc-sms-waiting",
        owner="hannah",
        title="SMS: your card is waiting",
        product=P.CREDIT_CARD,
        channel=Channel.SMS,
        tags=("sms",),
        first_run=3,
        versions=(
            "ClearPath: Your ClearPath Card application is almost done! Finish in 2 min and start with a 0% intro "
            "rate on purchases for 15 months. clearpath.example/c/fin",
        ),
        steps=(
            Submit(day(6, "15:00")),
            Claim(day(5, "09:30")),
            Accept(day(5, "09:35"), "sms.opt_out"),
            Accept(day(5, "09:36"), "sms.consent_record", "Attach the abandoned-application segment's consent export."),
            Accept(day(5, "09:38"), "card.apr_label", 'If the offer stays, it\'s "0% intro APR".'),
            Accept(day(5, "09:39"), "card.trigger_apr", "An intro rate triggers the go-to APR; won't fit in a text."),
            Decide(
                day(5, "09:45"),
                O.CHANGES_REQUESTED,
                'Needs "Reply STOP to opt out" and the consent export for the abandoned-application segment. The '
                "intro offer also needs the go-to APR; with 160 characters, link to the terms and keep the offer "
                "general.",
            ),
        ),
        expect=ItemStatus.CHANGES_REQUESTED,
    ),
    Story(
        key="cc-search-brand",
        owner="marcus",
        title="Paid search: ClearPath Card brand terms",
        product=P.CREDIT_CARD,
        channel=Channel.PAID_SEARCH,
        first_run=-9,
        versions=(
            "ClearPath Card | 0% Intro APR for 15 Months\n"
            "0% intro APR on purchases for 15 months, then 24.74%-33.74% variable APR. $0 annual fee. 3% transfer "
            f"fee. {ISSUER_LINE}",
        ),
        steps=(
            Submit(day(11, "10:40")),
            Claim(day(10, "09:20")),
            Checklist(day(10, "09:28")),
            Decide(
                day(10, "09:30"), O.APPROVED, "Current terms after the Prime move; every triggered disclosure is in."
            ),
            Place(day(10, "15:00"), "Google Ads: ClearPath Card brand campaign", first_run=-9),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="cc-lp-balance-transfer",
        owner="marcus",
        title="Balance transfer landing page",
        product=P.CREDIT_CARD,
        channel=Channel.LANDING_PAGE,
        tags=("balance-transfer",),
        first_run=10,
        versions=(
            "Transfer a balance. Breathe out.\n\n"
            "Move high-interest balances to the ClearPath Card and pay them down with a clear plan.\n\n"
            f"{NEW}\n\n"
            f"{ISSUER_LINE}",
        ),
        steps=(Submit(day(5, "16:30")), Claim(day(4, "11:00"))),
        expect=ItemStatus.IN_REVIEW,
    ),
    Story(
        key="cc-display-stale",
        owner="marcus",
        title="Card display: refresh after the Prime move",
        product=P.CREDIT_CARD,
        channel=Channel.DISPLAY,
        first_run=2,
        versions=(
            f"The ClearPath Card. {OLD}\n{ISSUER_LINE}",
            f"The ClearPath Card. {NEW}\n{ISSUER_LINE}",
        ),
        steps=(
            Submit(day(9, "11:00")),
            Claim(day(8, "13:30")),
            Accept(day(8, "13:35"), "pricing.terms_available", "Old APR range from before the Prime move."),
            Accept(day(8, "13:36"), "pricing.terms_current", quote="24.99%"),
            Checklist(day(8, "13:38")),
            Decide(
                day(8, "13:45"),
                O.APPROVED_WITH_EDITS,
                "Updated the APR range to the current 24.74%-33.74%; nothing else changed, so approving with the edit "
                "instead of another round.",
                edited=1,
            ),
        ),
        expect=ItemStatus.APPROVED,
    ),
    Story(
        key="cc-goldenstate-newsletter",
        owner="jordan",
        title="Golden State Saver newsletter: card spotlight",
        product=P.CREDIT_CARD,
        channel=Channel.EMAIL,
        partner="goldenstate",
        tags=("affiliate", "email"),
        first_run=8,
        last_run=8,
        versions=(
            "Subject: The card we'd use to pay down a balance\n\n"
            "Sponsored: Golden State Saver earns a commission from ClearPath if you're approved.\n\n"
            "This week's spotlight is the ClearPath Card.\n\n"
            f"{NEW}\n\n"
            f"{ISSUER_LINE}\n\n"
            "This is an advertisement. Unsubscribe at goldenstatesaver.example/unsubscribe.\n"
            "Golden State Saver Media, 1801 J Street, Sacramento, CA 95811",
        ),
        steps=(
            Submit(day(3, "12:15")),
            Assign(day(3, "12:40"), "leah", "Golden State is one of Leah's partners."),
        ),
        expect=ItemStatus.SUBMITTED,
    ),
    Story(
        key="cc-social-no-fees",
        owner="marcus",
        title="Paid social: no fees, no surprises",
        product=P.CREDIT_CARD,
        channel=Channel.PAID_SOCIAL,
        tags=("meta",),
        first_run=6,
        versions=(
            f"No fees. No surprises. Just the ClearPath Card.\n\n{NEW}\n\n{ISSUER_LINE}",
            "No annual fee and no surprises. Just the ClearPath Card.\n\n"
            "0% intro APR for 15 months from account opening, then a variable APR of 24.74% to 33.74%. Balance "
            "transfer fee: 3% of each transfer (min $5).",
        ),
        steps=(
            Submit(
                day(13, "10:20"),
                AiResult(
                    (
                        AiFinding(
                            "llm.net_impression",
                            "No fees. No surprises.",
                            '"No fees" may mislead: the card charges a 3% balance transfer fee.',
                            "No annual fee.",
                        ),
                    )
                ),
            ),
            Claim(day(12, "09:40")),
            Accept(day(12, "09:44"), "llm.net_impression", 'Right: the transfer fee makes "no fees" untrue.'),
            Decide(day(12, "09:50"), O.CHANGES_REQUESTED, '"No fees" isn\'t accurate with a 3% transfer fee.'),
            Resubmit(day(10, "14:00"), 1, 'Changed to "no annual fee".'),
            Claim(day(9, "09:30")),
            Accept(day(9, "09:34"), "card.issuer_line", "The Harborview issuer line dropped out of this version."),
            Comment(
                day(9, "09:40"),
                "Nearly there. The issuer line fell off when the copy was shortened; it has to be on every card ad.",
            ),
            Decide(day(9, "09:45"), O.CHANGES_REQUESTED, "Round 2: put the Harborview issuer line back."),
        ),
        expect=ItemStatus.CHANGES_REQUESTED,
    ),
    Story(
        key="cc-lp-rewards-relaunch",
        owner="marcus",
        title="Card landing page: everyday spending",
        product=P.CREDIT_CARD,
        channel=Channel.LANDING_PAGE,
        tags=("card-launch",),
        first_run=-6,
        versions=(
            "A card for the everyday.\n\n"
            "Groceries, gas, the dentist. Put them on one card with a clear plan to pay it down.\n\n"
            f"{OLD}\n\n"
            f"{ISSUER_LINE}",
        ),
        steps=(
            Submit(day(30, "09:30")),
            Claim(day(29, "14:10")),
            Checklist(day(29, "14:15")),
            Decide(day(29, "14:20"), O.APPROVED, "Standard terms block and issuer line; clean."),
            NewRound(day(9, "10:00")),
            Claim(day(8, "10:30")),
            Checklist(day(8, "10:36")),
            Decide(day(8, "10:40"), O.APPROVED, "New round from the generated version: current APRs, nothing else."),
            Place(
                day(7, "09:00"),
                "clearpath.example/card/everyday",
                first_run=-6,
                url="https://clearpath.example/card/everyday",
            ),
        ),
        expect=ItemStatus.APPROVED,
    ),
)
