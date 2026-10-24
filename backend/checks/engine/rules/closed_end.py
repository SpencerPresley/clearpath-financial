"""Closed-end credit (personal loans, mortgages): trigger terms, APR labeling, representative examples.

Regs table rows 1 and 2; Reg Z 1026.24(c)-(d).
"""

import re
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from checks.engine.amortization import monthly_payment
from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.rule import CLOSED_END, REGZ_1026_24, URL_1026_24, Hit, Rule, make_spec
from checks.engine.text import compile_i, first_span
from checks.engine.types import RuleContext, Span
from core.domain import Product, Severity

TRIGGER_APR = make_spec(
    "closed_end.trigger_apr",
    title="Trigger terms need the APR",
    citation="Reg Z 12 CFR 1026.24(d)(2)(iii)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=CLOSED_END,
    effective_from=REGZ_1026_24,
)
TRIGGER_REPAYMENT = make_spec(
    "closed_end.trigger_repayment",
    title="Trigger terms need the full repayment terms",
    citation="Reg Z 12 CFR 1026.24(d)(2)(ii)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=CLOSED_END,
    effective_from=REGZ_1026_24,
)
TRIGGER_DOWNPAYMENT = make_spec(
    "closed_end.trigger_downpayment",
    title="Mortgage trigger terms need the down payment",
    citation="Reg Z 12 CFR 1026.24(d)(2)(i)",
    url=URL_1026_24,
    severity=Severity.WARNING,
    products=frozenset({Product.MORTGAGE_PREQUAL}),
    effective_from=REGZ_1026_24,
)
RATE_MAY_INCREASE = make_spec(
    "closed_end.rate_may_increase",
    title="A variable rate needs to say it may increase",
    citation="Reg Z 12 CFR 1026.24(c), (d)(2)(iii)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=CLOSED_END,
    effective_from=REGZ_1026_24,
)
APR_LABEL = make_spec(
    "closed_end.apr_label",
    title='Rates are stated as an "APR"',
    citation="Reg Z 12 CFR 1026.24(c)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=CLOSED_END,
    effective_from=REGZ_1026_24,
)
OTHER_RATE = make_spec(
    "closed_end.other_rate",
    title="Other rates are no more conspicuous than the APR",
    citation="Reg Z 12 CFR 1026.24(c)",
    url=URL_1026_24,
    severity=Severity.WARNING,
    products=CLOSED_END,
    effective_from=REGZ_1026_24,
)
EXAMPLE_LABELED = make_spec(
    "closed_end.example_labeled",
    title="Representative examples are labeled as examples",
    citation="Reg Z 12 CFR 1026.24(d)(2), comment 24(d)(2)-5",
    url=URL_1026_24,
    severity=Severity.WARNING,
    products=CLOSED_END,
    effective_from=REGZ_1026_24,
)
EXAMPLE_PAYMENT = make_spec(
    "closed_end.example_payment",
    title="Example payments match the example's amount, term and APR",
    citation="Reg Z 12 CFR 1026.24(a), comment 24(d)(2)-5",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=CLOSED_END,
    effective_from=REGZ_1026_24,
)

_POINTS = compile_i(r"\b\d+(?:\.\d+)?\s+points?\b")
_DOWN_STATEMENT = compile_i(r"\bdown\s*payments?\b|(?:\bno|\bzero|\$0)\s+down\b")
_VARIABLE = compile_i(r"\bvariable(?:[-\s]rate)?\b|\badjustable(?:[-\s]rate)?\b|\brate\s+(?:may\s+)?adjusts?\b")
_ARM = re.compile(r"\bARM\b")  # case-sensitive: "arm" is an ordinary word
_MAY_INCREASE = compile_i(
    r"\b(?:may|can|could|will|might)\s+(?:be\s+)?(?:increase[ds]?|rise|go\s+up|adjust(?:ed)?|change[ds]?|vary)\b"
    r"|\bsubject\s+to\s+(?:change|increase)\b|\badjusts?\s+(?:annually|monthly|periodically|every)\b"
)
_EXAMPLE_LABEL = compile_i(r"\bexample\b|\be\.g\.|\bfor\s+instance\b|\brepresentative\b|\billustrat\w*|\bsample\b")
_TOLERANCE_UNITS = 1  # stated payment may differ from the computed one by one display unit ($1, or 1 cent)


def _triggers(a: Analysis) -> list[Span]:
    spans: list[Span] = [m.span for m in a.moneys if m.role in {"payment", "finance_charge", "down"}]
    spans += [t.span for t in a.credit_terms]
    spans += [p.span for p in a.percents if p.kind in {"down", "financing"} and p.value > 0]
    if a.product is Product.MORTGAGE_PREQUAL:
        spans += [Span(m.start(), m.end()) for m in _POINTS.finditer(a.text)]
    return sorted(spans, key=lambda s: s.start)


def _trigger_apr(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    triggers = _triggers(a)
    if triggers and not a.apr_rates:
        yield Hit(
            triggers[0],
            "This payment, term or cost figure needs the APR stated with it.",
            'Add the APR, e.g. "12.99% APR".',
        )


def _trigger_repayment(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    triggers = _triggers(a)
    has_payment = any(m.role == "payment" for m in a.moneys)
    has_length = bool(a.credit_terms)
    if triggers and not (has_payment and has_length):
        missing = "payment amount" if has_length else "number of payments or term"
        yield Hit(
            triggers[0],
            f"Show the full repayment terms with this figure; the {missing} is missing.",
            'e.g. "36 monthly payments of $337".',
        )


def _trigger_downpayment(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    triggers = _triggers(a)
    stated = (
        any(p.kind == "down" for p in a.percents)
        or any(m.role == "down" for m in a.moneys)
        or _DOWN_STATEMENT.search(a.text) is not None
    )
    if triggers and not stated:
        implied = next((p.span for p in a.percents if p.kind == "financing"), triggers[0])
        yield Hit(implied, "State the down payment alongside these terms.", 'e.g. "with 20% down".')


def _rate_may_increase(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if not any(p.kind == "rate" for p in a.percents) or _MAY_INCREASE.search(a.text):
        return
    candidates = [s for s in (first_span(_VARIABLE, a.text), first_span(_ARM, a.text)) if s is not None]
    if candidates:
        yield Hit(
            min(candidates, key=lambda s: s.start),
            "A variable rate needs a statement that it may increase after the loan is made.",
            '"The rate may increase after consummation."',
        )


def _apr_label(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if a.apr_rates:
        return
    for p in a.percents:
        if p.kind == "rate":
            yield Hit(p.span, 'State this rate as an "APR".', f'"{a.text[p.span.start : p.span.end]} APR"')


def _other_rate(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if not a.apr_rates:
        return
    for p in a.percents:
        if p.kind == "rate" and not p.apr_labeled:
            yield Hit(p.span, "Keep this rate no more prominent than the APR next to it.", None)


def _example_labeled(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for example in a.examples:
        para = a.segments.paragraph(example.payment.span.start)
        if not _EXAMPLE_LABEL.search(a.text, para.start, para.end):
            yield Hit(example.payment.span, "Label this as a representative example.", '"Example: …"')


def _example_payment(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for e in a.examples:
        unit = Decimal(1).scaleb(-e.payment.decimals)
        computed = monthly_payment(e.amount.value, e.apr.value, e.term.months).quantize(unit, ROUND_HALF_UP)
        if abs(e.payment.value - computed) > unit * _TOLERANCE_UNITS:
            shown = f"${computed:,.{e.payment.decimals}f}"
            yield Hit(
                e.payment.span,
                f"This payment doesn't match the example's amount, term and APR, which work out to {shown}.",
                shown,
            )


RULES: tuple[Rule, ...] = (
    Rule(TRIGGER_APR, _trigger_apr),
    Rule(TRIGGER_REPAYMENT, _trigger_repayment),
    Rule(TRIGGER_DOWNPAYMENT, _trigger_downpayment),
    Rule(RATE_MAY_INCREASE, _rate_may_increase),
    Rule(APR_LABEL, _apr_label),
    Rule(OTHER_RATE, _other_rate),
    Rule(EXAMPLE_LABELED, _example_labeled),
    Rule(EXAMPLE_PAYMENT, _example_payment),
)
