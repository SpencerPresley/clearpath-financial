"""One pass of shared analysis over the copy: every percent, dollar amount and term length, classified by its
surrounding words; representative examples; and the offer-terms claims (`TermsRefDraft` candidates).

Rules read this instead of re-scanning, so each number is classified once and every rule agrees on what a
number means.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from itertools import pairwise
from typing import Literal

from checks.engine.text import (
    DASH,
    RANGE_GAP,
    Segments,
    compile_i,
    decimals_of,
    to_decimal,
    window_after,
    window_before,
)
from checks.engine.types import Span
from core.domain import CreditCardTerms, PersonalLoanTerms, Product

Terms = PersonalLoanTerms | CreditCardTerms
PercentKind = Literal["rate", "fee", "down", "financing", "other"]  # financing: implied down payment
MoneyRole = Literal["payment", "finance_charge", "down", "annual_fee", "fee", "amount", "other"]
Qualifier = Literal["min", "max"]
RangeRole = Literal["lo", "hi"]
ClaimRole = Literal["min", "max", "value"]

CONTEXT = 32  # chars of context either side used to classify a number (about five words)
RANGE_GAP_MAX = 14  # "7.49% APR to 35.99%": the gap between the two ends of a range
EXAMPLE_REACH = 260  # how far from a payment to look for the rest of its representative example

# --- Patterns ------------------------------------------------------------------------------------------------

_PERCENT = re.compile(r"(?<![\w.,$])(?P<num>\d{1,3}(?:\.\d{1,3})?)(?:\s?%|\s?percent\b)", re.IGNORECASE)
_MONEY = re.compile(r"\$\s?(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<cents>\.\d{1,2})?(?P<k>[kK]\b)?(?![\d,]*\d)")
_TERM = compile_i(
    r"(?<![\w.$,/])(?P<n>\d{1,3})(?P<sep>\s*-\s*|\s+)(?P<unit>months?|mos?\b\.?|years?|yrs?\b\.?|"
    r"(?:monthly\s+)?payments)\b"
)
_TERM_RANGE = compile_i(
    rf"(?<![\w.$,/])(?P<a>\d{{1,3}})\s*(?:{DASH}|to|or)\s*(?P<b>\d{{1,3}})(?:\s*-\s*|\s+)(?P<unit>months?|years?)\b"
)

_MODIFIERS = r"(?:(?:intro(?:ductory)?|promo(?:tional)?|fixed|variable|purchase|standard|regular|ongoing|"
_MODIFIERS += r"balance[-\s]transfer|go-to|simple|annual)\s+)*"
_APR_WORD = r"(?:APRs?|annual\s+percentage\s+rates?)\b"
_AFTER_APR = compile_i(rf"\s*\(?\s*{_MODIFIERS}{_APR_WORD}")
_BEFORE_APR = compile_i(
    rf"{_APR_WORD}(?:\s*\(APR\))?\s*(?:[:=]|of|is|are|from|range\s+from|ranging\s+from|as\s+low\s+as|"
    r"starting\s+at|between|up\s+to|as\s+high\s+as)?\s*$"
)
_AFTER_FEE = compile_i(r"\s*(?:\w+\s+){0,3}?fees?\b|\s*of\s+(?:the|each|your)\s+(?:loan|amount|balance|transfer)")
_BEFORE_FEE = compile_i(
    r"fees?\s*(?:[:=]|of|is|are|from|up\s+to|between|ranging\s+from|as\s+low\s+as|starting\s+at)?\s*"
    rf"(?:\d+(?:\.\d+)?\s?%\s*(?:to|{DASH})\s*)?$"
)
_AFTER_DOWN = compile_i(r"\s*down\b")
_AFTER_FINANCING = compile_i(r"\s*(?:financing\b|LTV\b|loan[-\s]to[-\s]value)")
_BEFORE_DOWN = compile_i(r"down\s+payments?\s*(?:of|:|is)?\s*(?:as\s+little\s+as|just|only)?\s*$")
_AFTER_NONRATE = compile_i(
    r"\s*(?:cash\s*back|back\b|off\b|rewards?\b|discount|more\b|less\b|faster\b|savings?\b|"
    r"of\s+(?:customers|borrowers|applicants|people|users|members|our|all))"
)
_AFTER_RATE = compile_i(rf"\s*{_MODIFIERS}(?:interest|rates?\b|APY\b|intro(?:ductory)?\b|promo(?:tional)?\b)")
_BEFORE_RATE = compile_i(
    r"(?:rates?|interest(?:\s+rates?)?|as\s+low\s+as|starting\s+at|starts\s+at|from|at)\s*(?:[:=]|of|is|are)?\s*"
    r"(?:just|only)?\s*$"
)
_BEFORE_MIN = compile_i(
    r"(?:as\s+low\s+as|starting\s+(?:at|from)|starts?\s+at|from|low\s+as|as\s+little\s+as|minimum(?:\s+of)?|"
    r"at\s+least)\s*(?:just|only)?\s*$"
)
_BEFORE_MAX = compile_i(r"(?:up\s+to|as\s+high\s+as|as\s+much\s+as|max(?:imum)?(?:\s+of)?|no\s+more\s+than)\s*$")
_INTRO_WORD = compile_i(r"\bintro(?:ductory)?\b")
_PROMO_WORD = compile_i(r"\bpromo(?:tional)?\b")
# A label in front of the number only counts when it leads straight into it: "intro APR of 0%", "Intro rate: 0%".
# "After the intro period, a 19.99% APR" is about the go-to rate, not an intro rate.
_LEADING_LABEL = compile_i(
    r"\b(?P<label>intro(?:ductory)?|promo(?:tional)?)\s+(?:(?:purchase|balance[-\s]transfer)\s+)?"
    r"(?:APRs?|rates?|annual\s+percentage\s+rates?)?\s*(?:of|:|is|at)?\s*(?:just|only)?\s*$"
)
_PROMO_PERIOD = compile_i(r"^[^.%]{0,40}?\b(?:for\s+(?:the\s+first\s+)?\d+\s+(?:months|billing\s+cycles)|until\b)")
_FOR_MONTHS = compile_i(r"\bfor\s+(?:the\s+first\s+)?(?P<n>\d{1,3})\s+(?:months|billing\s+cycles)\b")
_ORIGINATION = compile_i(r"\borigination\b")
_BALANCE_TRANSFER = compile_i(r"\bbalance[-\s]transfers?\b")
_CASH_ADVANCE = compile_i(r"\b(?:cash\s+advance|penalty)\b")

_AFTER_PAYMENT = compile_i(
    r"\s*(?:/\s?mo(?:nth)?\b\.?|per\s+month|a\s+month|each\s+month|every\s+month|monthly\b|/\s?wk\b|"
    r"per\s+week|a\s+week|weekly\b|bi-?weekly\b)"
)
_MONTHLY_AFTER = compile_i(r"\s*(?:/\s?mo(?:nth)?\b|per\s+month|a\s+month|each\s+month|every\s+month|monthly\b)")
_BEFORE_PAYMENT = compile_i(
    r"(?:payments?|pay(?:ing)?)\s*(?:of|as\s+low\s+as|from|starting\s+at|is|are|:|would\s+be|will\s+be|"
    r"just|only)?\s*(?:just|only)?\s*$"
)
_BEFORE_MONTHLY = compile_i(r"monthly\s+(?:payments?|installments?)\s*(?:of|:|is|are|would\s+be|will\s+be)?\s*$")
_AFTER_FINANCE = compile_i(
    r"\s*(?:in\s+(?:total\s+)?(?:interest|finance\s+charges?)|total\s+(?:interest|cost\s+of\s+credit|"
    r"finance\s+charges?)|finance\s+charges?|interest\s+charges?|total\s+cost\b)"
)
_BEFORE_FINANCE = compile_i(
    r"(?:finance\s+charges?|total\s+(?:interest|cost\s+of\s+credit)|interest\s+charges?|total\s+cost)\s*"
    r"(?:of|:|is|would\s+be|will\s+be)?\s*$"
)
_AFTER_ANNUAL_FEE = compile_i(r"\s*annual\s+(?:membership\s+)?fee")
_BEFORE_ANNUAL_FEE = compile_i(r"annual\s+(?:membership\s+)?fee\s*(?:of|:|is)?\s*$")
_AFTER_OTHER_FEE = compile_i(r"\s*(?:\w+\s+){0,2}fees?\b")
_BEFORE_AMOUNT = compile_i(
    r"(?:borrow|loans?(?:\s+amounts?)?|amounts?|get|access|up\s+to|from|between|as\s+much\s+as|"
    r"as\s+little\s+as)\b[^$]{0,15}$"
)
_AFTER_AMOUNT = compile_i(r"\s*(?:personal\s+)?loans?\b")

_TERM_CREDIT_BEFORE = compile_i(r"\b(?:terms?|repay(?:ment)?|over|loans?|mortgages?|pay\s*off|payoff|financ\w*)\b")
_TERM_CREDIT_AFTER = compile_i(r"^\s*(?:terms?|loans?|repayment|to\s+repay|of\s+payments|fixed|mortgage|ARM)\b")
_TERM_NONCREDIT_AFTER = compile_i(
    r"^\s*(?:of\s+(?:experience|service|business|history|helping)|in\s+business|history|track\s+record|"
    r"warranty|anniversary|old)\b"
)

_NO_ANNUAL_FEE = compile_i(r"\bno\s+annual\s+(?:membership\s+)?fees?\b")
_NO_ORIGINATION_FEE = compile_i(r"\bno\s+origination\s+fees?\b")


# --- Mentions ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PercentMention:
    span: Span
    number: Span
    value: Decimal
    decimals: int
    apr_labeled: bool
    kind: PercentKind
    intro_labeled: bool
    promotional: bool
    qualifier: Qualifier | None
    qualifier_start: int | None  # where "as low as" / "up to" begins, for quoting the whole claim
    range_role: RangeRole | None
    origination: bool
    balance_transfer: bool
    cash_advance: bool


@dataclass(frozen=True)
class MoneyMention:
    span: Span
    value: Decimal
    decimals: int
    grouped: bool
    thousands_suffix: bool
    role: MoneyRole
    monthly: bool
    qualifier: Qualifier | None
    range_role: RangeRole | None


@dataclass(frozen=True)
class TermMention:
    span: Span  # the number only
    count: int
    unit: Literal["month", "year", "payment"]
    months: int
    credit_context: bool
    qualifier: Qualifier | None
    range_role: RangeRole | None


@dataclass(frozen=True)
class Example:
    amount: MoneyMention
    term: TermMention
    apr: PercentMention
    payment: MoneyMention

    @property
    def extent(self) -> Span:
        parts = (self.amount.span, self.term.span, self.apr.span, self.payment.span)
        return Span(min(p.start for p in parts), max(p.end for p in parts))

    def covers(self, span: Span) -> bool:
        return self.extent.start <= span.start and span.end <= self.extent.end


@dataclass(frozen=True)
class Claim:
    field: str
    span: Span
    value: Decimal
    role: ClaimRole


@dataclass(frozen=True)
class Analysis:
    text: str
    product: Product
    segments: Segments
    percents: tuple[PercentMention, ...]
    moneys: tuple[MoneyMention, ...]
    terms: tuple[TermMention, ...]
    examples: tuple[Example, ...]
    claims: tuple[Claim, ...]

    @cached_property
    def rates(self) -> tuple[PercentMention, ...]:
        return tuple(p for p in self.percents if p.kind == "rate")

    @cached_property
    def apr_rates(self) -> tuple[PercentMention, ...]:
        return tuple(p for p in self.percents if p.kind == "rate" and p.apr_labeled)

    @cached_property
    def credit_terms(self) -> tuple[TermMention, ...]:
        in_examples = {e.term.span for e in self.examples}
        return tuple(t for t in self.terms if t.credit_context or t.span in in_examples)

    @cached_property
    def has_rate_range(self) -> bool:
        return any(p.range_role == "lo" and p.kind == "rate" for p in self.percents)


# --- Classification ------------------------------------------------------------------------------------------


def _qualifier(before: str) -> Qualifier | None:
    if _BEFORE_MIN.search(before):
        return "min"
    if _BEFORE_MAX.search(before):
        return "max"
    return None


# First match wins. Each row: (kind, pattern matched at the start of the text after the number, pattern
# matched at the end of the text before it). None = no pattern on that side.
_PERCENT_KINDS: tuple[tuple[PercentKind, re.Pattern[str] | None, re.Pattern[str] | None], ...] = (
    ("fee", _AFTER_FEE, _BEFORE_FEE),
    ("down", _AFTER_DOWN, _BEFORE_DOWN),
    ("financing", _AFTER_FINANCING, None),
    ("other", _AFTER_NONRATE, None),
    ("rate", _AFTER_RATE, _BEFORE_RATE),
)


def _classify[K: str](
    rows: tuple[tuple[K, re.Pattern[str] | None, re.Pattern[str] | None], ...], before: str, after: str
) -> K | None:
    for kind, after_pattern, before_pattern in rows:
        if (after_pattern and after_pattern.match(after)) or (before_pattern and before_pattern.search(before)):
            return kind
    return None


def _percent_kind(before: str, after: str, *, apr_labeled: bool) -> PercentKind:
    if apr_labeled:
        return "rate"
    return _classify(_PERCENT_KINDS, before, after) or "other"


@dataclass
class _RawPercent:
    span: Span
    number: Span
    value: Decimal
    decimals: int
    before: str
    after: str
    sentence: Span
    apr_labeled: bool
    apr_label_text: str
    kind: PercentKind
    qualifier: Qualifier | None
    qualifier_start: int | None
    range_role: RangeRole | None = None


def _qualifier_start(before: str, pos: int) -> int | None:
    m = _BEFORE_MIN.search(before) or _BEFORE_MAX.search(before)
    return pos - len(before) + m.start() if m else None


def _scan_percents(text: str, segments: Segments) -> list[_RawPercent]:
    raw: list[_RawPercent] = []
    prev_end = 0
    for m in _PERCENT.finditer(text):
        s, e = m.start(), m.end()
        sentence = segments.sentence(s)
        before = window_before(text, s, CONTEXT, max(sentence.start, prev_end))
        after = window_after(text, e, CONTEXT, sentence.end)
        label = _AFTER_APR.match(after)
        apr_labeled = label is not None or _BEFORE_APR.search(before) is not None
        raw.append(
            _RawPercent(
                span=Span(s, e),
                number=Span(m.start("num"), m.end("num")),
                value=to_decimal(m.group("num")),
                decimals=decimals_of(m.group("num")),
                before=before,
                after=after,
                sentence=sentence,
                apr_labeled=apr_labeled,
                apr_label_text=label.group(0) if label else "",
                kind=_percent_kind(before, after, apr_labeled=apr_labeled),
                qualifier=_qualifier(before),
                qualifier_start=_qualifier_start(before, s),
            )
        )
        prev_end = e + (label.end() if label else 0)  # the next number's context starts after this label
    for lo, hi in pairwise(raw):
        gap = text[lo.span.end : hi.span.start]
        if len(gap) <= RANGE_GAP_MAX and RANGE_GAP.fullmatch(gap) and lo.range_role is None:
            lo.range_role, hi.range_role = "lo", "hi"
            labeled = lo.apr_labeled or hi.apr_labeled
            lo.apr_labeled = hi.apr_labeled = labeled
            kind = lo.kind if lo.kind != "other" else hi.kind
            if labeled:
                kind = "rate"
            lo.kind = hi.kind = kind
            hi.qualifier = hi.qualifier_start = None
    return raw


def _percents(text: str, segments: Segments, product: Product, terms: Terms | None) -> tuple[PercentMention, ...]:
    raw = _scan_percents(text, segments)
    out: list[PercentMention] = []
    for i, r in enumerate(raw):
        partner = raw[i - 1] if r.range_role == "hi" else raw[i + 1] if r.range_role == "lo" else None
        lead = partner if r.range_role == "hi" and partner is not None else r
        tail = partner if r.range_role == "lo" and partner is not None else r
        context = lead.before + text[lead.span.start : tail.span.end] + tail.after
        leading = _LEADING_LABEL.search(lead.before)
        leading_word = leading.group("label") if leading else ""
        intro = bool(_INTRO_WORD.search(leading_word) or _INTRO_WORD.search(tail.apr_label_text))
        promo = intro or bool(_PROMO_WORD.search(leading_word) or _PROMO_WORD.search(tail.apr_label_text))
        if product is Product.CREDIT_CARD and r.kind == "rate" and not promo:
            promo = bool(_PROMO_PERIOD.match(tail.after))
            if isinstance(terms, CreditCardTerms) and r.value < terms.purchase_apr_min:
                promo = True
        out.append(
            PercentMention(
                span=r.span,
                number=r.number,
                value=r.value,
                decimals=r.decimals,
                apr_labeled=r.apr_labeled,
                kind=r.kind,
                intro_labeled=intro,
                promotional=promo,
                qualifier=lead.qualifier,
                qualifier_start=lead.qualifier_start,
                range_role=r.range_role,
                origination=bool(_ORIGINATION.search(context)),
                balance_transfer=bool(_BALANCE_TRANSFER.search(context)),
                cash_advance=bool(_CASH_ADVANCE.search(context)),
            )
        )
    return tuple(out)


_MONEY_ROLES: tuple[tuple[MoneyRole, re.Pattern[str] | None, re.Pattern[str] | None], ...] = (
    ("down", _AFTER_DOWN, _BEFORE_DOWN),
    ("payment", _AFTER_PAYMENT, _BEFORE_PAYMENT),
    ("payment", None, _BEFORE_MONTHLY),
    ("finance_charge", _AFTER_FINANCE, _BEFORE_FINANCE),
    ("annual_fee", _AFTER_ANNUAL_FEE, _BEFORE_ANNUAL_FEE),
    ("fee", _AFTER_OTHER_FEE, None),
    ("amount", _AFTER_AMOUNT, _BEFORE_AMOUNT),
)


def _money_role(before: str, after: str, value: Decimal) -> MoneyRole:
    role = _classify(_MONEY_ROLES, before, after) or "other"
    return "other" if role == "down" and value == 0 else role  # "$0 down" states no down payment


@dataclass
class _RawMoney:
    span: Span
    value: Decimal
    decimals: int
    grouped: bool
    thousands_suffix: bool
    role: MoneyRole
    monthly: bool
    qualifier: Qualifier | None
    range_role: RangeRole | None = None

    def freeze(self) -> MoneyMention:
        return MoneyMention(
            span=self.span,
            value=self.value,
            decimals=self.decimals,
            grouped=self.grouped,
            thousands_suffix=self.thousands_suffix,
            role=self.role,
            monthly=self.monthly,
            qualifier=self.qualifier,
            range_role=self.range_role,
        )


def _moneys(text: str, segments: Segments) -> tuple[MoneyMention, ...]:
    found: list[_RawMoney] = []
    prev_end = 0
    for m in _MONEY.finditer(text):
        s, e = m.start(), m.end()
        sentence = segments.sentence(s)
        before = window_before(text, s, CONTEXT, max(sentence.start, prev_end))
        after = window_after(text, e, CONTEXT, sentence.end)
        value = to_decimal(m.group("num") + (m.group("cents") or ""))
        if m.group("k"):
            value *= 1000
        role = _money_role(before, after, value)
        monthly = role == "payment" and bool(_MONTHLY_AFTER.match(after) or _BEFORE_MONTHLY.search(before))
        found.append(
            _RawMoney(
                span=Span(s, e),
                value=value,
                decimals=decimals_of(m.group("cents") or ""),
                grouped="," in m.group("num"),
                thousands_suffix=bool(m.group("k")),
                role=role,
                monthly=monthly,
                qualifier=_qualifier(before),
            )
        )
        prev_end = e
    for lo, hi in pairwise(found):
        gap = text[lo.span.end : hi.span.start]
        if len(gap) <= RANGE_GAP_MAX and RANGE_GAP.fullmatch(gap) and lo.range_role is None:
            lo.range_role, hi.range_role = "lo", "hi"
            hi.qualifier = None
            if "amount" in (lo.role, hi.role):
                lo.role = hi.role = "amount"
            elif lo.role != "other":
                hi.role = lo.role
    return tuple(f.freeze() for f in found)


def _unit(raw: str) -> Literal["month", "year", "payment"]:
    word = raw.lower()
    if word.startswith(("y",)):
        return "year"
    if "payment" in word:
        return "payment"
    return "month"


def _term_context(text: str, segments: Segments, start: int, end: int, *, hyphenated: bool) -> bool:
    sentence = segments.sentence(start)
    after = window_after(text, end, CONTEXT, sentence.end)
    if _TERM_NONCREDIT_AFTER.match(after):
        return False
    if hyphenated or _TERM_CREDIT_AFTER.match(after):
        return True
    before = window_before(text, start, CONTEXT, sentence.start)
    return bool(_TERM_CREDIT_BEFORE.search(before))


def _terms(text: str, segments: Segments) -> tuple[TermMention, ...]:
    out: list[TermMention] = []
    taken: list[Span] = []
    for m in _TERM_RANGE.finditer(text):
        unit = _unit(m.group("unit"))
        credit = _term_context(text, segments, m.start(), m.end(), hyphenated=False)
        sentence = segments.sentence(m.start())
        qualifier = _qualifier(window_before(text, m.start(), CONTEXT, sentence.start))
        for group, role in (("a", "lo"), ("b", "hi")):
            count = int(m.group(group))
            out.append(
                TermMention(
                    span=Span(m.start(group), m.end(group)),
                    count=count,
                    unit=unit,
                    months=count * 12 if unit == "year" else count,
                    credit_context=credit,
                    qualifier=qualifier if role == "lo" else None,
                    range_role=role,  # type: ignore[arg-type]
                )
            )
        taken.append(Span(m.start(), m.end()))
    for m in _TERM.finditer(text):
        if any(t.start <= m.start() < t.end for t in taken):
            continue
        unit = _unit(m.group("unit"))
        count = int(m.group("n"))
        hyphenated = "-" in m.group("sep")
        sentence = segments.sentence(m.start())
        before = window_before(text, m.start(), CONTEXT, sentence.start)
        out.append(
            TermMention(
                span=Span(m.start("n"), m.end("n")),
                count=count,
                unit=unit,
                months=count * 12 if unit == "year" else count,
                credit_context=unit == "payment"
                or _term_context(text, segments, m.start(), m.end(), hyphenated=hyphenated),
                qualifier=_qualifier(before),
                range_role=None,
            )
        )
    out.sort(key=lambda t: t.span.start)
    return tuple(out)


def _nearest[T: (PercentMention, MoneyMention, TermMention)](items: list[T], pos: int) -> T | None:
    return min(items, key=lambda m: abs(m.span.start - pos), default=None)


def _examples(
    segments: Segments,
    percents: tuple[PercentMention, ...],
    moneys: tuple[MoneyMention, ...],
    terms: tuple[TermMention, ...],
) -> tuple[Example, ...]:
    out: list[Example] = []
    for pay in moneys:
        if pay.role != "payment" or not pay.monthly:
            continue
        para = segments.paragraph(pay.span.start)
        lo = max(para.start, pay.span.start - EXAMPLE_REACH)
        hi = min(para.end, pay.span.end + EXAMPLE_REACH)

        def near(span: Span, lo: int = lo, hi: int = hi) -> bool:
            return lo <= span.start and span.end <= hi

        aprs = [p for p in percents if p.kind == "rate" and p.apr_labeled and p.range_role is None and near(p.span)]
        lengths = [t for t in terms if t.unit in {"month", "year"} and t.range_role is None and near(t.span)]
        amounts = [
            m
            for m in moneys
            if m.role in {"amount", "other"} and m.range_role is None and m.value > pay.value and near(m.span)
        ]
        apr = _nearest(aprs, pay.span.start)
        term = _nearest(lengths, pay.span.start)
        amount = _nearest(amounts, pay.span.start)
        if apr and term and amount:
            out.append(Example(amount=amount, term=term, apr=apr, payment=pay))
    return tuple(out)


# --- Claims (offer-terms references) -------------------------------------------------------------------------


def _bound_field(value: Decimal, lo_field: str, hi_field: str, terms: Terms) -> tuple[str, ClaimRole] | None:
    """Field of an unqualified single value, decided only by equality with the current terms."""
    if value == getattr(terms, lo_field):
        return lo_field, "min"
    if value == getattr(terms, hi_field):
        return hi_field, "max"
    return None


def _range_field(
    p: PercentMention | MoneyMention | TermMention, lo_field: str, hi_field: str
) -> tuple[str, ClaimRole] | None:
    if p.range_role is not None:
        return (lo_field, "min") if p.range_role == "lo" else (hi_field, "max")
    if p.qualifier is not None:
        return (lo_field, "min") if p.qualifier == "min" else (hi_field, "max")
    return None


def _personal_loan_percent_claims(a: Analysis, terms: PersonalLoanTerms) -> Iterator[Claim]:
    for p in a.percents:
        if p.kind == "rate" and p.apr_labeled:
            hit = _range_field(p, "apr_min", "apr_max") or _bound_field(p.value, "apr_min", "apr_max", terms)
        elif p.kind == "fee" and p.origination:
            fields = ("origination_fee_min_pct", "origination_fee_max_pct")
            hit = _range_field(p, *fields) or _bound_field(p.value, *fields, terms)
        else:
            hit = None
        if hit:
            yield Claim(hit[0], p.span, p.value, hit[1])


def _personal_loan_claims(a: Analysis, terms: PersonalLoanTerms) -> list[Claim]:
    def in_example(span: Span) -> bool:
        return any(e.covers(span) for e in a.examples)

    claims = list(_personal_loan_percent_claims(a, terms))
    claims.extend(
        Claim(hit[0], m.span, m.value, hit[1])
        for m in a.moneys
        if m.role == "amount" and not in_example(m.span) and (hit := _range_field(m, "amount_min", "amount_max"))
    )
    for t in a.credit_terms:
        if t.unit != "year" and not in_example(t.span):
            role = _range_field(t, "min", "max")
            claims.append(Claim("term_months", t.span, Decimal(t.count), role[1] if role else "value"))
    claims.extend(
        Claim("origination_fee_max_pct", span, Decimal(0), "value")
        for span in _phrase_spans(_NO_ORIGINATION_FEE, a.text)
    )
    claims.extend(Claim("example_payment", e.payment.span, e.payment.value, "value") for e in a.examples)
    return claims


def _credit_card_claims(a: Analysis, terms: CreditCardTerms) -> list[Claim]:
    claims: list[Claim] = []
    for p in a.percents:
        if p.kind == "rate" and p.apr_labeled and not p.cash_advance:
            if p.promotional:
                claims.append(Claim("intro_apr", p.span, p.value, "value"))
                if months := _FOR_MONTHS.search(a.text, p.span.end, min(len(a.text), p.span.end + 60)):
                    claims.append(Claim("intro_months", Span(months.start("n"), months.end("n")),
                                        Decimal(months.group("n")), "value"))  # fmt: skip
                continue
            hit = _range_field(p, "purchase_apr_min", "purchase_apr_max") or _bound_field(
                p.value, "purchase_apr_min", "purchase_apr_max", terms
            )
            if hit:
                claims.append(Claim(hit[0], p.span, p.value, hit[1]))
        elif p.kind == "fee" and p.balance_transfer:
            claims.append(Claim("balance_transfer_fee_pct", p.span, p.value, "value"))
    claims.extend(Claim("annual_fee", m.span, m.value, "value") for m in a.moneys if m.role == "annual_fee")
    claims.extend(Claim("annual_fee", span, Decimal(0), "value") for span in _phrase_spans(_NO_ANNUAL_FEE, a.text))
    return claims


def _phrase_spans(pattern: re.Pattern[str], text: str) -> list[Span]:
    return [Span(m.start(), m.end()) for m in pattern.finditer(text)]


def analyze(text: str, product: Product, terms: Terms | None) -> Analysis:
    segments = Segments(text)
    percents = _percents(text, segments, product, terms)
    moneys = _moneys(text, segments)
    term_mentions = _terms(text, segments)
    examples = _examples(segments, percents, moneys, term_mentions)
    analysis = Analysis(text, product, segments, percents, moneys, term_mentions, examples, ())
    if isinstance(terms, PersonalLoanTerms):
        claims = _personal_loan_claims(analysis, terms)
    elif isinstance(terms, CreditCardTerms):
        claims = _credit_card_claims(analysis, terms)
    else:
        claims = []
    claims.sort(key=lambda c: (c.span.start, c.field))
    return Analysis(text, product, segments, percents, moneys, term_mentions, examples, tuple(claims))
