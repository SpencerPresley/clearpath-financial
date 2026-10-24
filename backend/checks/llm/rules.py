"""The judgment rules the LLM pre-review evaluates.

Code owns facts (numbers against offer terms, required strings, banned phrases); these rules are the calls a
pattern can't make: whether a qualifier works in substance, whether a claim is scoped to the right step, what the
copy as a whole implies. Each `guidance` is rendered verbatim into the cached system prompt, so editing one is a
prompt change: bump `checks.llm.prompt.PROMPT_VERSION`.

Every rule is a warning. A model's judgment is a prompt to look, not a detected fact, and spec §4.2 ruling 3
already requires every finding, warnings included, to be triaged before Approve.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from checks.engine.rule import (
    ALL_PRODUCTS,
    FEDERAL,
    FTC_255_5,
    REGB_1002_4,
    REGZ_1026_16,
    REGZ_1026_24,
    UNVERSIONED,
    URL_255_5,
    URL_1002_4,
    URL_1026_24,
    URL_SH24,
    applies,
)
from checks.engine.types import RuleContext, RuleSpec
from core.domain import PARTNER_CHANNELS, Product, Severity

URL_5536 = "https://www.govinfo.gov/link/uscode/12/5536?type=usc&year=mostrecent&link-type=html"


@dataclass(frozen=True)
class LlmRule:
    spec: RuleSpec
    guidance: str  # what to flag and what not to flag; rendered into the system prompt
    default_message: str  # used when the model's own message breaks the copy rules (spec §5.4)
    # Code rules that already report the same problem. An LLM finding of this rule whose span overlaps a code
    # finding of one of these is dropped as a duplicate.
    code_counterparts: frozenset[str] = frozenset()
    partner_only: bool = False  # applies only to partner content (mirrors endorsement.material_connection)


def _spec(  # noqa: PLR0913 - keywords mirror RuleSpec's facets
    rule_id: str,
    *,
    title: str,
    citation: str,
    url: str,
    effective_from: date,
    products: frozenset[Product] = ALL_PRODUCTS,
) -> RuleSpec:
    return RuleSpec(
        id=rule_id,
        title=title,
        citation=citation,
        url=url,
        severity=Severity.WARNING,
        kind="llm",
        products=products,
        channels=None,
        markets=FEDERAL,
        effective_from=effective_from,
    )


CREDITWORTHINESS = LlmRule(
    spec=_spec(
        "llm.creditworthiness_qualifier",
        title='"As low as" rates say who gets them',
        citation="CFPB Supervisory Highlights Issue 24 §2.9.1; Reg Z 12 CFR 1026.24(a), 1026.16(a)",
        url=URL_SH24,
        effective_from=REGZ_1026_16,
    ),
    guidance=(
        'Flag a claim that emphasizes the lowest rate ("as low as 7.49%", "starting at 7.49%", "rates from 7.49%" '
        "with no upper end) when the copy does not tell the reader, in substance, that the rate they get depends on "
        'their credit. Wording that does the job: "based on your credit", "rates depend on your creditworthiness", '
        '"the lowest rates are for applicants with excellent credit". Wording that does not: "rates may vary", '
        '"terms apply", "subject to change", or a qualifier the copy itself contradicts ("excellent credit not '
        'required"). A full range ("APRs from 7.49% to 35.99%") is a range, not a lowest-rate claim; do not flag '
        "it under this rule. Quote the lowest-rate claim."
    ),
    default_message="This lowest-rate claim may need to say that rates depend on creditworthiness.",
    code_counterparts=frozenset({"pricing.creditworthiness_qualifier"}),
)

CREDIT_INQUIRY_SCOPE = LlmRule(
    spec=_spec(
        "llm.credit_inquiry_scope",
        title="Credit-check claims match the actual inquiry",
        citation="CFPB Supervisory Highlights Issue 24 §2.8.2; 12 U.S.C. 5536",
        url=URL_SH24,
        effective_from=UNVERSIONED,
    ),
    guidance=(
        "Checking a rate uses a soft inquiry that does not affect credit scores; applying for or accepting the "
        "credit involves a hard inquiry that can. Flag two kinds of claim. First, a claim that there is no credit "
        'check at all ("no credit check", "without checking your credit"), even one limited to seeing a rate: a '
        'soft inquiry is still a credit check. Second, a score-impact claim ("won\'t affect your credit score", '
        '"zero impact on your score", or any paraphrase) worded to cover applying, approval or the whole process: '
        '"Apply with no impact to your credit". Do not flag a score-impact claim explicitly limited to checking a '
        'rate or prequalifying ("Checking your rate won\'t affect your credit score"). Quote the claim.'
    ),
    default_message="This credit-check claim may not match the inquiry made; limit it to checking a rate.",
    code_counterparts=frozenset({"claims.credit_impact"}),
)

MATERIAL_CONNECTION = LlmRule(
    spec=_spec(
        "llm.material_connection",
        title="Paid relationship is disclosed clearly",
        citation="FTC 16 CFR 255.5; Reg Z comment 2(a)(2)-2; CFPB Supervisory Highlights Issue 37",
        url=URL_255_5,
        effective_from=FTC_255_5,
    ),
    guidance=(
        "Applies only to content published by a partner that ClearPath pays (affiliate, lead generator, "
        "marketplace or influencer). Flag a disclosure of that paid relationship that is unclear or out of place: "
        'vague ("we work with partners", "#sp", "#collab", "thanks ClearPath"), placed only after the endorsement '
        'or behind a link, or contradicted by a claim like "unbiased", "independent review" or "not sponsored". '
        'Influencer posts need wording like "#ad" or "Paid partnership with ClearPath" near the start. Do not flag '
        "a clear disclosure placed before or beside the endorsement. If the code findings already report a missing "
        "disclosure, skip this rule. Quote the inadequate disclosure or the contradicting claim."
    ),
    default_message="The paid relationship may need a clearer disclosure next to the endorsement.",
    code_counterparts=frozenset({"endorsement.material_connection"}),
    partner_only=True,
)

DISCOURAGING_STATEMENT = LlmRule(
    spec=_spec(
        "llm.discouraging_statement",
        title="Wording doesn't discourage applicants on a prohibited basis",
        citation="Reg B 12 CFR 1002.4(b) (text effective 2026-07-21)",
        url=URL_1002_4,
        effective_from=REGB_1002_4,
    ),
    guidance=(
        "The prohibited bases are race, color, religion, national origin, sex, marital status, age, receipt of "
        "public-assistance income, and exercising rights under the Consumer Credit Protection Act. Flag wording "
        "a reasonable person would read as saying ClearPath would deny an application, or offer worse terms, "
        'because of one of these: "not for retirees", "English speakers only", "married couples get the best '
        'rates", "no public assistance income". Do not flag outreach that welcomes a group without discouraging '
        'others ("Se habla español", "first-time borrowers welcome") or real credit criteria (income, credit '
        "history, ability to repay). Judge the text only; images and targeting are reviewed by a person. Quote the "
        "phrase."
    ),
    default_message="This wording may discourage some applicants on a prohibited basis.",
)

NET_IMPRESSION = LlmRule(
    spec=_spec(
        "llm.net_impression",
        title="Overall impression matches the actual offer",
        citation=("12 U.S.C. 5531, 5536(a)(1)(B); Reg Z 12 CFR 1026.24(a), 1026.16(a); mortgages: Reg N 12 CFR 1014.3"),
        url=URL_5536,
        effective_from=REGZ_1026_16,
    ),
    guidance=(
        "Judge what a reasonable consumer takes away from the copy as a whole. Flag a specific express or implied "
        'claim likely to mislead about the cost, availability, speed or nature of the credit: "free money" or '
        '"cash gift" for a loan; "instant approval" or "money in minutes" stated without limits; "no fees" or '
        '"no hidden fees" when the offer terms include a fee; "bad credit OK" or "everyone qualifies" implying '
        'approval regardless of credit; "lowest rates anywhere" or "#1 lender" with no stated basis; "wipe out '
        'your debt" or "be debt-free" for a loan that only moves the debt; fine print that takes back the headline. '
        'Do not flag ordinary puffery ("simple", "fast application", "friendly support"), accurate claims, or '
        "numbers that differ from the offer terms (code checks those). Use this rule only when no more specific "
        "rule covers the claim. Quote the claim."
    ),
    default_message="This claim may give a misleading impression of the offer.",
    code_counterparts=frozenset({"claims.guaranteed", "claims.preapproved"}),
)

PRESSURE_TACTICS = LlmRule(
    spec=_spec(
        "llm.pressure_tactics",
        title="Deadlines and scarcity are real and stated plainly",
        citation="12 U.S.C. 5531, 5536(a)(1)(B)",
        url=URL_5536,
        effective_from=UNVERSIONED,
    ),
    guidance=(
        "Flag urgency or scarcity language that pressures a borrowing decision without a stated, specific basis: "
        '"Act now before rates go up!", "Only 3 loans left today", "Offer expires at midnight", "Apply in the '
        'next 10 minutes", "Rates this low won\'t last". The offer terms carry no deadlines, so the reviewer has '
        "to confirm any deadline is real; the message should ask for that. Do not flag a dated promotion stated "
        'plainly ("Intro APR offer ends December 31, 2026") or a neutral call to action ("Apply today", "Check '
        'your rate"). Quote the pressure phrase.'
    ),
    default_message="Confirm this deadline or scarcity claim is real, or remove it.",
)

MORTGAGE_COMPARISON = LlmRule(
    spec=_spec(
        "llm.mortgage_comparison",
        title="Payment and rate comparisons show the full picture",
        citation="Reg Z 12 CFR 1026.24(i)(2); Reg N 12 CFR 1014.3(h)",
        url=URL_1026_24,
        effective_from=REGZ_1026_24,
        products=frozenset({Product.MORTGAGE_PREQUAL}),
    ),
    guidance=(
        "Flag a comparison between the reader's current or a hypothetical payment or rate and the advertised "
        'loan, express or implied: "Save $300 a month", "Cut your payment in half", "Drop your rate from 7% to '
        '5%". It needs every rate or payment that will apply over the full term and how long each applies. Do '
        "not flag a plain statement of the advertised terms with no comparison. Quote the comparison."
    ),
    default_message="This payment or rate comparison may need every rate or payment over the loan term.",
)

LLM_RULES: tuple[LlmRule, ...] = (
    CREDITWORTHINESS,
    CREDIT_INQUIRY_SCOPE,
    MATERIAL_CONNECTION,
    DISCOURAGING_STATEMENT,
    NET_IMPRESSION,
    PRESSURE_TACTICS,
    MORTGAGE_COMPARISON,
)


def _index(rules: tuple[LlmRule, ...]) -> Mapping[str, LlmRule]:
    by_id: dict[str, LlmRule] = {}
    for rule in rules:
        if rule.spec.id in by_id:
            raise ValueError(f"duplicate LLM rule id {rule.spec.id}")
        by_id[rule.spec.id] = rule
    return MappingProxyType(by_id)


LLM_RULES_BY_ID: Mapping[str, LlmRule] = _index(LLM_RULES)
# The LLM rule-set date: the latest date any LLM rule (as written) took effect. Moves only when the law does; a
# check-result cache must also key on PROMPT_VERSION and the model name.
LLM_RULESET_VERSION = max(rule.spec.effective_from for rule in LLM_RULES)


def _is_partner_content(ctx: RuleContext) -> bool:
    return ctx.partner_type is not None or ctx.channel in PARTNER_CHANNELS


def applicable_rules(ctx: RuleContext) -> tuple[LlmRule, ...]:
    return tuple(
        rule for rule in LLM_RULES if applies(rule.spec, ctx) and (not rule.partner_only or _is_partner_content(ctx))
    )
