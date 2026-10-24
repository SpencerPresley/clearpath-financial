"""Credit card (open-end) advertising: trigger terms, intro rates, deferred interest, "fixed", issuer line.

Regs table rows 4-7 (card parts); Reg Z 1026.16.
"""

import re
from collections.abc import Iterable

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis, PercentMention
from checks.engine.format import money, pct, purchase_apr
from checks.engine.rule import (
    REGZ_1026_16,
    UNVERSIONED,
    URL_1026_16,
    URL_COMPANY_FACTS,
    Hit,
    Rule,
    insert_after,
    instruct,
    make_spec,
    replace_with,
)
from checks.engine.text import compile_i, first_span, phrase_pattern, window_after, window_before
from checks.engine.types import RuleContext, Span
from core.domain import CreditCardTerms, Product, Severity

CARD = frozenset({Product.CREDIT_CARD})


APR_LABEL = make_spec(
    "card.apr_label",
    title='Card rates are stated as an "APR"',
    citation="Reg Z 12 CFR 1026.16(b)(1)(ii)",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
TRIGGER_APR = make_spec(
    "card.trigger_apr",
    title="Card trigger terms need the purchase APR",
    citation="Reg Z 12 CFR 1026.16(b)(1)(ii), comment 16(b)(1)-1",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
APR_VARIABLE = make_spec(
    "card.apr_variable",
    title="A variable purchase APR says it's variable",
    citation="Reg Z 12 CFR 1026.16(b)(1)(ii)",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
TRIGGER_ANNUAL_FEE = make_spec(
    "card.trigger_annual_fee",
    title="Card trigger terms need the annual fee",
    citation="Reg Z 12 CFR 1026.16(b)(1)(iii)",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
TRIGGER_TRANSACTION_FEES = make_spec(
    "card.trigger_transaction_fees",
    title="Balance transfer offers state the transfer fee",
    citation="Reg Z 12 CFR 1026.16(b)(1)(i)",
    url=URL_1026_16,
    severity=Severity.WARNING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
INTRO_LABEL = make_spec(
    "card.intro_label",
    title='Intro rates say "intro" or "introductory" in the same phrase',
    citation="Reg Z 12 CFR 1026.16(g)(3), comment 16(g)-2",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
INTRO_TERMS = make_spec(
    "card.intro_terms",
    title="The first intro rate listing gives its end and the go-to APR in the same paragraph",
    citation="Reg Z 12 CFR 1026.16(g)(4), comment 16(g)-3",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
DEFERRED_INTEREST = make_spec(
    "card.deferred_interest",
    title='Deferred interest offers say "if paid in full" and when interest is charged',
    citation="Reg Z 12 CFR 1026.16(h)(3)-(4), comments 16(h)-3, -4",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
FIXED_APR = make_spec(
    "card.fixed_apr",
    title='A "fixed" APR states how long it is fixed',
    citation="Reg Z 12 CFR 1026.16(f)",
    url=URL_1026_16,
    severity=Severity.BLOCKING,
    products=CARD,
    effective_from=REGZ_1026_16,
)
ISSUER_LINE = make_spec(
    "card.issuer_line",
    title="Card ads name the issuing bank",
    # Shown to users, so no internal doc names or caveats here. The caveat, for maintainers: this is ClearPath card
    # program policy (docs/decisions.md, "Company facts"); its legal basis is unverified and it may only be practice.
    citation="ClearPath card program policy",
    url=URL_COMPANY_FACTS,
    severity=Severity.WARNING,
    products=CARD,
    effective_from=UNVERSIONED,
)

_NEGATIVE_TRIGGER = compile_i(
    r"\bno\s+(?:annual\s+(?:membership\s+)?fees?|interest\b|(?:foreign\s+transaction\s+|balance\s+transfer\s+)?fees?\b)"
)
_FEE_WORDS = compile_i(
    r"\b(?:late|annual|balance[-\s]transfer|cash\s+advance|foreign\s+transaction|over-?limit|returned\s+payment)"
    r"\s+fees?\b"
)
_ANNUAL_FEE_STATEMENT = compile_i(r"\bannual\s+(?:membership\s+)?fees?\b|\bmembership\s+fees?\b")
_BT_MENTION = compile_i(r"\bbalance[-\s]transfers?\b|\btransfer\s+(?:a|your)\s+balances?\b")
_BT_FEE = compile_i(
    r"\b(?:balance[-\s])?transfer\s+fees?\b|\bfees?\s+(?:for|on)\s+(?:each\s+)?(?:balance\s+)?transfers?\b"
)
_VARIABLE = compile_i(r"\bvariable\b")
_APR_NEXT = re.compile(r"[ \t]+APR\b")  # the rate is followed by its "APR" label
_PERIOD = compile_i(
    r"\bfor\s+(?:the\s+first\s+)?\d+\s+(?:months|billing\s+cycles|years)\b|\buntil\s+\w+|\bthrough\s+\w+"
)
_DEFERRED = compile_i(r"\bno\s+interest\b|\bsame[-\s]as[-\s]cash\b|\bdeferred\s+interest\b")
_IF_PAID_IN_FULL = compile_i(r"\bif\s+(?:the\s+(?:promotional\s+)?balance\s+is\s+)?paid\s+in\s+full\b")
_MONTH_NAME = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
_DEFERRED_PERIOD = compile_i(
    rf"\b(?:for|within|in|until|by|before)\s+(?:the\s+first\s+)?(?:\d+\s+(?:months|days)|{_MONTH_NAME}\b)"
)
_PERIOD_LENGTH = compile_i(rf"\b\d+\s+(?:months|days)\b|\b{_MONTH_NAME}(?:\s+\d{{1,2}}(?:,\s+\d{{4}})?)?\b")
_PURCHASE_DATE_WARNING = compile_i(
    r"\binterest\s+will\s+be\s+charged\b.{0,80}?\bfrom\s+the\s+(?:original\s+)?(?:purchase\s+date|date\s+of\s+"
    r"(?:the\s+)?purchase)"
)
_NOT_PAID_IN_FULL = compile_i(r"\bnot\s+paid\s+in\s+full\b")
_GRACE_PERIOD = compile_i(r"\bin\s+full\s+(?:each|every)\s+(?:month|billing\s+cycle)\b|\bgrace\s+period\b")
_FIXED = compile_i(r"\bfixed\b")
_RATE_WORD = compile_i(r"\b(?:APRs?|rates?)\b")
_ANY_ISSUER = compile_i(r"\bissued\s+by\s+\w")
_PHRASE_REACH = 30


def _triggers(a: Analysis) -> list[Span]:
    spans = [p.span for p in a.percents if p.kind in {"rate", "fee"}]
    spans += [m.span for m in a.moneys if m.role in {"annual_fee", "fee", "finance_charge"}]
    spans += [Span(m.start(), m.end()) for m in _NEGATIVE_TRIGGER.finditer(a.text)]
    spans += [Span(m.start(), m.end()) for m in _FEE_WORDS.finditer(a.text)]
    return sorted(spans, key=lambda s: s.start)


def _purchase_aprs(a: Analysis) -> list[PercentMention]:
    return [p for p in a.apr_rates if not p.promotional and not p.cash_advance]


def _promotional(a: Analysis) -> list[PercentMention]:
    return [p for p in a.rates if p.promotional and p.range_role != "hi"]


def _apr_label(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for p in a.rates:
        if not p.apr_labeled:
            yield replace_with(p.span, 'State this rate as an "APR".', f"{a.text[p.span.start : p.span.end]} APR")


def _card_terms(ctx: RuleContext) -> CreditCardTerms | None:
    return ctx.terms if isinstance(ctx.terms, CreditCardTerms) else None


def _trigger_apr(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    triggers = _triggers(a)
    if triggers and not _purchase_aprs(a):
        terms = _card_terms(ctx)
        message = "Rate, fee and no-fee claims need the purchase APR stated too."
        yield insert_after(triggers[0], message, f" ({purchase_apr(terms)})") if terms else Hit(triggers[0], message)


def _apr_variable(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if not (isinstance(ctx.terms, CreditCardTerms) and ctx.terms.purchase_apr_variable):
        return
    aprs = _purchase_aprs(a)
    for i, p in enumerate(aprs):
        if p.range_role == "hi":
            continue
        end = aprs[i + 1].span.end if p.range_role == "lo" and i + 1 < len(aprs) else p.span.end
        sentence = a.segments.sentence(p.span.start)
        phrase = window_before(a.text, p.span.start, _PHRASE_REACH, sentence.start) + a.text[p.span.start : end]
        phrase += window_after(a.text, end, _PHRASE_REACH, sentence.end)
        if not _VARIABLE.search(phrase):
            message = 'The purchase APR is variable; say "variable APR".'
            # "19.99% APR" takes " variable" after the rate; a range or "APR of 19.99%" is for a person to reword.
            if p.range_role is None and _APR_NEXT.match(a.text, p.span.end):
                yield insert_after(p.span, message, " variable", shown='"variable APR"')
            else:
                yield instruct(p.span, message, '"variable APR"')


def _trigger_annual_fee(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    triggers = _triggers(a)
    if triggers and not _ANNUAL_FEE_STATEMENT.search(a.text):
        terms = _card_terms(ctx)
        message = "State the annual fee, even if it's $0."
        fee = f" ({money(terms.annual_fee)} annual fee)" if terms is not None else None
        yield insert_after(triggers[0], message, fee) if fee else Hit(triggers[0], message)


def _trigger_transaction_fees(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    mention = first_span(_BT_MENTION, a.text)
    has_fee = _BT_FEE.search(a.text) or any(p.kind == "fee" and p.balance_transfer for p in a.percents)
    if mention and not has_fee:
        terms = _card_terms(ctx)
        message = "State the balance transfer fee with the transfer offer."
        fee = f" ({pct(terms.balance_transfer_fee_pct)} balance transfer fee)" if terms is not None else None
        yield insert_after(mention, message, fee) if fee else Hit(mention, message)


def _intro_label(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for p in _promotional(a):
        if not p.intro_labeled:
            rate = a.text[p.number.start : p.number.end]  # the copy's own rate
            message = 'Put "intro" or "introductory" in the same phrase as this rate.'
            if _APR_NEXT.match(a.text, p.span.end):  # "0% APR": " intro" goes between them
                yield insert_after(p.span, message, " intro", shown=f'"{rate}% intro APR"')
            else:
                yield replace_with(p.span, message, f"{rate}% intro APR")


def _intro_terms(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    promos = _promotional(a)
    if not promos:
        return
    first = promos[0]
    para = a.segments.paragraph(first.span.start)
    terms = _card_terms(ctx)
    if not _PERIOD.search(a.text, para.start, para.end):
        months = terms.intro_months if terms is not None else None
        fix = f'"for {months} months"' if months is not None else None
        yield instruct(first.span, "Say when the intro rate ends in the same paragraph.", fix)
    go_to = [p for p in _purchase_aprs(a) if para.start <= p.span.start < para.end]
    if not go_to:
        fix = f'"then {purchase_apr(terms)}"' if terms is not None else None
        yield instruct(first.span, "Give the APR that applies after the intro period in the same paragraph.", fix)


def _deferred_offers(a: Analysis) -> list[re.Match[str]]:
    """Statements that describe a deferred-interest offer. A grace period ("pay in full each month and pay no
    interest") is excluded by 16(h)(2), and a 0% intro APR described as "no interest" is a promotional rate under
    16(g), not deferred interest (comment 16(h)-1)."""
    offers = []
    for m in _DEFERRED.finditer(a.text):
        sentence = a.segments.sentence(m.start())
        if m.group(0).lower().startswith("no"):
            if _GRACE_PERIOD.search(a.text, sentence.start, sentence.end):
                continue
            if any(p.promotional and p.value == 0 and sentence.start <= p.span.start < sentence.end for p in a.rates):
                continue
        offers.append(m)
    return offers


def _offer_period(a: Analysis, at: int) -> str | None:
    """The period the copy itself states in the paragraph at `at` ("6 months", "December"), if any. Card terms carry
    no deferred-interest period, so a suggestion can only reuse the copy's."""
    para = a.segments.paragraph(at)
    found = _PERIOD_LENGTH.search(a.text, para.start, para.end)
    return found.group(0) if found else None


def _deferred_interest(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    offers = _deferred_offers(a)
    for m in offers:
        sentence = a.segments.sentence(m.start())
        paid = _IF_PAID_IN_FULL.search(a.text, sentence.start, sentence.end)
        period = _DEFERRED_PERIOD.search(a.text, sentence.start, sentence.end)
        if paid is None or period is None or period.start() < paid.start():
            length = _offer_period(a, m.start())
            yield instruct(
                Span(m.start(), m.end()),
                'State the deferred-interest period with "if paid in full" in front of it, in the same phrase.',
                f'"No interest if paid in full within {length}"' if length is not None else None,
            )
    if offers:
        first = offers[0]
        para = a.segments.paragraph(first.start())
        warned = _PURCHASE_DATE_WARNING.search(a.text, para.start, para.end) and _NOT_PAID_IN_FULL.search(
            a.text, para.start, para.end
        )
        if not warned:
            length = _offer_period(a, first.start())
            within = f" within {length}" if length is not None else ""
            yield instruct(
                Span(first.start(), first.end()),
                "Add, in the same paragraph, that interest is charged from the purchase date if the balance isn't "
                "paid in full. If this is a 0% intro APR instead, call it one.",
                '"Interest will be charged to your account from the purchase date if the promotional balance is not '
                f'paid in full{within}."',
            )


def _fixed_apr(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    variable = isinstance(ctx.terms, CreditCardTerms) and ctx.terms.purchase_apr_variable
    for m in _FIXED.finditer(a.text):
        sentence = a.segments.sentence(m.start())
        near = window_before(a.text, m.start(), _PHRASE_REACH, sentence.start)
        near += window_after(a.text, m.end(), _PHRASE_REACH, sentence.end)
        if not _RATE_WORD.search(near) or _PERIOD.search(a.text, sentence.start, sentence.end):
            continue
        message = 'Say how long the rate is fixed, or drop "fixed".'
        if variable:
            message = 'The purchase APR is variable under current terms; drop "fixed" or state the fixed period.'
        # No suggestion: the terms carry no fixed period, so any number here would be invented.
        yield Hit(Span(m.start(), m.end()), message, None)


def _issuer_line(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if isinstance(ctx.terms, CreditCardTerms):
        bank = ctx.terms.issuing_bank
        pattern = re.compile(rf"\bissued\s+by\s+{phrase_pattern(bank)}", re.IGNORECASE)
        fix = f'"The ClearPath Card is issued by {bank.removesuffix(".")}."'  # "Bank, N.A." ends in one
    else:
        pattern, fix = _ANY_ISSUER, None
    if not pattern.search(a.text):
        yield instruct(None, "Name the bank that issues the card.", fix)


RULES: tuple[Rule, ...] = (
    Rule(APR_LABEL, _apr_label),
    Rule(TRIGGER_APR, _trigger_apr),
    Rule(APR_VARIABLE, _apr_variable),
    Rule(TRIGGER_ANNUAL_FEE, _trigger_annual_fee),
    Rule(TRIGGER_TRANSACTION_FEES, _trigger_transaction_fees),
    Rule(INTRO_LABEL, _intro_label),
    Rule(INTRO_TERMS, _intro_terms),
    Rule(DEFERRED_INTEREST, _deferred_interest),
    Rule(FIXED_APR, _fixed_apr),
    Rule(ISSUER_LINE, _issuer_line),
)
