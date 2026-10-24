"""Pricing claims: "as low as" qualifiers and every quoted number against current offer terms (regs table row 3;
bait pricing under Reg Z 1026.24(a) / 1026.16(a)).
"""

import re
from collections.abc import Iterable, Iterator
from decimal import Decimal

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.format import apr_bounds, money, pct
from checks.engine.rule import (
    ALL_PRODUCTS,
    REGZ_1026_16,
    URL_1026_24,
    URL_SH24,
    Hit,
    Rule,
    instruct,
    make_spec,
    replace_with,
)
from checks.engine.text import compile_i
from checks.engine.types import RuleContext, Span
from core.domain import CreditCardTerms, PersonalLoanTerms, Product, Severity

TERMS_PRODUCTS = frozenset({Product.PERSONAL_LOAN, Product.CREDIT_CARD})
_SH24_CITATION = "Reg Z 12 CFR 1026.24(a), 1026.16(a); CFPB Supervisory Highlights Issue 24 §2.9.1"

AS_LOW_AS_RANGE = make_spec(
    "pricing.as_low_as_range",
    title='"As low as" rates need the full range',
    citation=_SH24_CITATION,
    url=URL_SH24,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=REGZ_1026_16,
)
CREDITWORTHINESS = make_spec(
    "pricing.creditworthiness_qualifier",
    title='"As low as" rates need a creditworthiness qualifier',
    citation="CFPB Supervisory Highlights Issue 24 §2.9.1",
    url=URL_SH24,
    severity=Severity.WARNING,
    products=ALL_PRODUCTS,
    effective_from=REGZ_1026_16,
)
TERMS_AVAILABLE = make_spec(
    "pricing.terms_available",
    title="Quoted terms are actually offered under current offer terms",
    citation="Reg Z 12 CFR 1026.24(a) (closed-end), 1026.16(a) (open-end)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=TERMS_PRODUCTS,
    effective_from=REGZ_1026_16,
)
TERMS_CURRENT = make_spec(
    "pricing.terms_current",
    title="Quoted lowest and highest values match current offer terms",
    citation="Reg Z 12 CFR 1026.24(a), 1026.16(a)",
    url=URL_1026_24,
    severity=Severity.WARNING,
    products=TERMS_PRODUCTS,
    effective_from=REGZ_1026_16,
)

_QUALIFIER = compile_i(
    r"\bcredit\s?worth\w*|\bbased\s+on\s+(?:your\s+)?credit\b|\bdepend(?:s|ing)?\s+on\s+(?:your\s+)?credit\b"
    r"|\bmost\s+(?:credit[-\s]?)?(?:qualified|creditworthy)\b|\b(?:excellent|best|strongest|top)\s+credit\b"
    r"|\bwell[-\s]qualified\b|\bhighest\s+credit\b|\bqualified\s+(?:applicants|borrowers)\b"
)


def _lowest_rate_claims(a: Analysis, *, standalone: bool) -> list[Span]:
    """ "as low as 7.49%", "starting at", "rates from"; `standalone` skips "from X% to Y%" (already a range)."""
    return [
        Span(p.qualifier_start, p.span.end)
        for p in a.rates
        if p.qualifier == "min" and p.qualifier_start is not None and not (standalone and p.range_role is not None)
    ]


def _as_low_as_range(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if a.has_rate_range:
        return
    # The range on offer now (walkthrough B2); no terms (mortgage prequal), no numbers to suggest.
    bounds = apr_bounds(ctx.terms)
    fix = f'"APRs from {pct(bounds[0])} to {pct(bounds[1])}"' if bounds is not None else None
    for span in _lowest_rate_claims(a, standalone=True):
        yield instruct(span, "Show the full rate range next to this lowest rate.", fix)


def _creditworthiness(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if _QUALIFIER.search(a.text):
        return
    for span in _lowest_rate_claims(a, standalone=False):
        yield instruct(
            span,
            "Say that the lowest rates go to the most creditworthy applicants.",
            '"Your rate depends on your creditworthiness; the lowest rates are for the most qualified applicants."',
        )


def _outside(value: Decimal, lo: Decimal, hi: Decimal) -> bool:
    return not lo <= value <= hi


def _nearest(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    """The offered value closest to one that isn't offered: the bound it overshoots."""
    return min(max(value, lo), hi)


def _pl_rates(a: Analysis, t: PersonalLoanTerms) -> Iterator[Hit]:
    apr_range = f"{pct(t.apr_min)}\u2013{pct(t.apr_max)}"
    for p in a.rates:
        if _outside(p.value, t.apr_min, t.apr_max):
            nearest = pct(_nearest(p.value, t.apr_min, t.apr_max))
            yield replace_with(p.span, f"This APR isn't offered; current APRs are {apr_range}.", nearest, shown=nearest)


def _pl_amounts_and_terms(a: Analysis, t: PersonalLoanTerms) -> Iterator[Hit]:
    amount_range = f"{money(t.amount_min)}\u2013{money(t.amount_max)}"
    for m in a.moneys:
        if m.role == "amount" and _outside(m.value, t.amount_min, t.amount_max):
            nearest = money(_nearest(m.value, t.amount_min, t.amount_max))
            message = f"This loan amount isn't offered; current amounts are {amount_range}."
            yield replace_with(m.span, message, nearest, shown=nearest)
    offered = ", ".join(str(n) for n in t.term_months)
    for term in a.credit_terms:
        if term.months not in t.term_months:
            yield Hit(term.span, f"This term isn't offered; current terms are {offered} months.", None)


def _pl_fees(a: Analysis, t: PersonalLoanTerms) -> Iterator[Hit]:
    fee_range = f"{pct(t.origination_fee_min_pct)}\u2013{pct(t.origination_fee_max_pct)}"
    for p in a.percents:
        if (
            p.kind == "fee"
            and p.origination
            and _outside(p.value, t.origination_fee_min_pct, t.origination_fee_max_pct)
        ):
            nearest = pct(_nearest(p.value, t.origination_fee_min_pct, t.origination_fee_max_pct))
            message = f"This origination fee isn't current; fees are {fee_range}."
            yield replace_with(p.span, message, nearest, shown=nearest)
    for c in a.claims:
        if c.field == "origination_fee_max_pct" and c.value == 0 and t.origination_fee_max_pct > 0:
            yield Hit(c.span, f"Origination fees currently run {fee_range}, so this claim isn't accurate.", None)


def _personal_loan_available(a: Analysis, t: PersonalLoanTerms) -> Iterator[Hit]:
    yield from _pl_rates(a, t)
    yield from _pl_amounts_and_terms(a, t)
    yield from _pl_fees(a, t)


def _card_rates(a: Analysis, t: CreditCardTerms) -> Iterator[Hit]:
    apr_range = f"{pct(t.purchase_apr_min)}\u2013{pct(t.purchase_apr_max)}"
    for p in a.rates:
        if p.cash_advance:
            continue
        if p.promotional:
            if t.intro_apr is None:
                yield Hit(p.span, "There's no intro APR in the current card terms.", None)
            elif p.value != t.intro_apr:
                intro = pct(t.intro_apr)
                yield replace_with(p.span, f"The current intro APR is {intro}.", intro, shown=intro)
        elif _outside(p.value, t.purchase_apr_min, t.purchase_apr_max):
            nearest = pct(_nearest(p.value, t.purchase_apr_min, t.purchase_apr_max))
            message = f"This APR isn't offered; current purchase APRs are {apr_range}."
            yield replace_with(p.span, message, nearest, shown=nearest)


def _card_claims(a: Analysis, t: CreditCardTerms) -> Iterator[Hit]:
    intro_months = None if t.intro_months is None else Decimal(t.intro_months)
    for c in a.claims:
        if c.field == "intro_months" and c.value != intro_months:
            message = (
                "There's no intro period in the current card terms."
                if intro_months is None
                else f"The current intro period is {intro_months} months."
            )
            yield Hit(c.span, message, None)
        elif c.field == "balance_transfer_fee_pct" and c.value != t.balance_transfer_fee_pct:
            yield Hit(c.span, f"The current balance transfer fee is {pct(t.balance_transfer_fee_pct)}.", None)
        elif c.field == "annual_fee" and c.value != t.annual_fee:
            yield Hit(c.span, f"The current annual fee is {money(t.annual_fee)}.", None)


def _card_available(a: Analysis, t: CreditCardTerms) -> Iterator[Hit]:
    yield from _card_rates(a, t)
    yield from _card_claims(a, t)


def _terms_available(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if isinstance(ctx.terms, PersonalLoanTerms):
        yield from _personal_loan_available(a, ctx.terms)
    elif isinstance(ctx.terms, CreditCardTerms):
        yield from _card_available(a, ctx.terms)


_BOUNDS: dict[str, tuple[str, str]] = {
    "apr_min": ("apr_min", "apr_max"),
    "apr_max": ("apr_min", "apr_max"),
    "amount_min": ("amount_min", "amount_max"),
    "amount_max": ("amount_min", "amount_max"),
    "origination_fee_min_pct": ("origination_fee_min_pct", "origination_fee_max_pct"),
    "origination_fee_max_pct": ("origination_fee_min_pct", "origination_fee_max_pct"),
    "purchase_apr_min": ("purchase_apr_min", "purchase_apr_max"),
    "purchase_apr_max": ("purchase_apr_min", "purchase_apr_max"),
}


def _terms_current(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    terms = ctx.terms
    if terms is None:
        return
    for c in a.claims:
        if c.role == "value":
            continue
        if c.field == "term_months" and isinstance(terms, PersonalLoanTerms):
            bound = Decimal(min(terms.term_months) if c.role == "min" else max(terms.term_months))
            within = int(c.value) in terms.term_months
        elif c.field in _BOUNDS:
            lo_field, hi_field = _BOUNDS[c.field]
            lo, hi = getattr(terms, lo_field), getattr(terms, hi_field)
            bound = lo if c.field == lo_field else hi
            within = lo <= c.value <= hi
        else:
            continue
        if within and c.value != bound:
            which = "lowest" if c.role == "min" else "highest"
            shown = _formatted(c.field, bound)
            message = f"The current {which} value is {shown}; update this to match."
            quote = a.text[c.span.start : c.span.end]
            if _same_shape(quote, shown):
                yield replace_with(c.span, message, shown, shown=shown)
            else:
                yield instruct(c.span, message, shown)


def _formatted(field: str, value: Decimal) -> str:
    """A terms value as copy writes it: "11.11%", "$44,000", "60 months"."""
    if field == "term_months":
        return f"{value} months"
    return money(value) if field.startswith("amount") else pct(value)


_FIGURE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _same_shape(quote: str, literal: str) -> bool:
    """Whether the claim's span is a bare figure of the same kind as the literal ("$25,000" for "$44,000"), so
    swapping one for the other leaves the sentence intact."""
    same_kind = quote.startswith("$") == literal.startswith("$") and quote.endswith("%") == literal.endswith("%")
    return _FIGURE.fullmatch(quote) is not None and _FIGURE.fullmatch(literal) is not None and same_kind


RULES: tuple[Rule, ...] = (
    Rule(AS_LOW_AS_RANGE, _as_low_as_range),
    Rule(CREDITWORTHINESS, _creditworthiness),
    Rule(TERMS_AVAILABLE, _terms_available),
    Rule(TERMS_CURRENT, _terms_current),
)
