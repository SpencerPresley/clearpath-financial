"""Rule primitives shared by every rule family: what a check returns and how a spec is built."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.types import FindingDraft, RuleContext, RuleSpec, Span
from core.domain import Channel, FindingSource, Market, Product, Severity

ALL_PRODUCTS = frozenset(Product)
CLOSED_END = frozenset({Product.PERSONAL_LOAN, Product.MORTGAGE_PREQUAL})
FEDERAL = frozenset(Market)
CALIFORNIA = frozenset({Market.CA})

# effective_from = date of the current version of the cited CFR section per the eCFR versioner API (fetched
# 2026-10-24). 2017-01-01 is eCFR's point-in-time baseline, i.e. "unchanged since at least then". Sources with
# no versioned record (statute-only, California code, ClearPath policy) use that same baseline rather than the
# adoption date: a long-standing rule must not silently drop out of a context whose `today` is earlier.
REGZ_1026_24 = date(2017, 1, 1)
REGZ_1026_16 = date(2020, 2, 28)
REGN_1014 = date(2017, 1, 1)
REGV_1022_54 = date(2017, 1, 1)
REGB_1002_12 = date(2023, 8, 29)
REGB_1002_4 = date(2026, 7, 21)
TCPA_64_1200 = date(2026, 3, 25)
CANSPAM_16_CFR_316 = date(2016, 12, 22)
FTC_255_5 = date(2023, 7, 26)
UNVERSIONED = date(2017, 1, 1)  # statute, state code or policy; not eCFR-versioned

URL_1026_24 = "https://www.consumerfinance.gov/rules-policy/regulations/1026/24/"
URL_1026_16 = "https://www.consumerfinance.gov/rules-policy/regulations/1026/16/"
URL_1014 = "https://www.ecfr.gov/current/title-12/part-1014"
URL_1022_54 = "https://www.consumerfinance.gov/rules-policy/regulations/1022/54/"
URL_1002_4 = "https://www.consumerfinance.gov/rules-policy/regulations/1002/4/"
URL_1002_12 = "https://www.ecfr.gov/current/title-12/section-1002.12"
URL_SH24 = "https://files.consumerfinance.gov/f/documents/cfpb_supervisory-highlights_issue-24_2021-06.pdf"
URL_PRIME_CHOICE = "https://files.consumerfinance.gov/f/documents/cfpb_prime-choice-funding_consent-order_2020-07.pdf"
URL_64_1200 = "https://www.ecfr.gov/current/title-47/section-64.1200"
URL_7704 = "https://www.govinfo.gov/content/pkg/USCODE-2023-title15/html/USCODE-2023-title15-chap103-sec7704.htm"
URL_255_5 = "https://www.ecfr.gov/current/title-16/section-255.5"
URL_CA_22162 = "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=FIN&sectionNum=22162"
URL_COMPANY_FACTS = (
    "https://github.com/SpencerPresley/clearpath-financial/blob/main/docs/decisions.md"
    "#company-facts-fictional-chosen-for-consistency"
)


@dataclass(frozen=True)
class Hit:
    """One thing a check found. `span` is None when the finding is about something missing from the copy."""

    span: Span | None
    message: str
    suggested_fix: str | None = None


CheckFn = Callable[[RuleContext, Analysis, EngineConfig], Iterable[Hit]]


@dataclass(frozen=True)
class Rule:
    spec: RuleSpec
    check: CheckFn


def make_spec(  # noqa: PLR0913 - a spec has this many facets; keywords keep call sites readable
    rule_id: str,
    *,
    title: str,
    citation: str,
    url: str,
    severity: Severity,
    products: frozenset[Product],
    effective_from: date,
    kind: Literal["code", "human"] = "code",
    channels: frozenset[Channel] | None = None,
    markets: frozenset[Market] = FEDERAL,
) -> RuleSpec:
    return RuleSpec(
        id=rule_id,
        title=title,
        citation=citation,
        url=url,
        severity=severity,
        kind=kind,
        products=products,
        channels=channels,
        markets=markets,
        effective_from=effective_from,
    )


def applies(spec: RuleSpec, ctx: RuleContext) -> bool:
    if ctx.product not in spec.products:
        return False
    if spec.channels is not None and ctx.channel not in spec.channels:
        return False
    # Federal rules (every market) apply wherever the content runs, even if no market was recorded.
    if spec.markets != FEDERAL and spec.markets.isdisjoint(ctx.markets):
        return False
    return spec.effective_from <= ctx.today


def to_finding(spec: RuleSpec, hit: Hit, text: str) -> FindingDraft:
    source = FindingSource.CODE if spec.kind == "code" else FindingSource.HUMAN
    return FindingDraft(
        rule_id=spec.id,
        source=source,
        severity=spec.severity,
        message=hit.message,
        citation=spec.citation,
        suggested_fix=hit.suggested_fix,
        span=hit.span,
        quote=text[hit.span.start : hit.span.end] if hit.span is not None else None,
    )
