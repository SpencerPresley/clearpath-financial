"""Re-render copy under new offer terms: replace each referenced number, recompute example payments.

Works from `(field, span, quoted_value)` alone, which is all a persisted TermsRef keeps: anything else (a term
length's role, a representative example's parts) is re-derived by re-analyzing the original text.

A field whose new value is None (e.g. the intro offer was dropped) is left as written. The generated version
then fails `pricing.terms_available` in the code checks, so it can't slip through a one-click approval.
"""

import re
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

from checks.engine.amortization import monthly_payment
from checks.engine.extract import Analysis, Example, analyze
from checks.engine.types import Span, TermsRefDraft
from core.domain import CreditCardTerms, PersonalLoanTerms

Terms = PersonalLoanTerms | CreditCardTerms

REFERENCEABLE: dict[type[PersonalLoanTerms | CreditCardTerms], frozenset[str]] = {
    PersonalLoanTerms: frozenset(
        {
            "apr_min",
            "apr_max",
            "amount_min",
            "amount_max",
            "term_months",
            "origination_fee_min_pct",
            "origination_fee_max_pct",
            "example_payment",
        }
    ),
    CreditCardTerms: frozenset(
        {"purchase_apr_min", "purchase_apr_max", "intro_apr", "intro_months", "balance_transfer_fee_pct", "annual_fee"}
    ),
}

_PERCENT = re.compile(r"(?P<num>\d+(?:\.\d+)?)(?P<suffix>\s?(?:%|percent))", re.IGNORECASE)
_MONEY = re.compile(r"(?P<prefix>\$\s?)(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<cents>\.\d+)?(?P<k>[kK])?")
_INTEGER = re.compile(r"\d+")
_NO_FEE = re.compile(
    r"(?P<no>no)\s+(?P<kind>annual|origination)(?P<rest>\s+(?:membership\s+)?)(?P<fee>fees?)", re.IGNORECASE
)


def _fullmatch(pattern: re.Pattern[str], quote: str) -> re.Match[str]:
    m = pattern.fullmatch(quote)
    if m is None:
        raise ValueError(f"can't re-render {quote!r}")
    return m


def _parse(quote: str) -> Decimal | None:
    if m := _PERCENT.fullmatch(quote):
        return Decimal(m.group("num"))
    if m := _MONEY.fullmatch(quote):
        value = Decimal(m.group("num").replace(",", "") + (m.group("cents") or ""))
        return value * 1000 if m.group("k") else value
    if _INTEGER.fullmatch(quote):
        return Decimal(quote)
    if _NO_FEE.fullmatch(quote):
        return Decimal(0)
    return None


def _places_needed(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _format_percent(quote: str, new: Decimal) -> str:
    m = _fullmatch(_PERCENT, quote)
    places = max(len(m.group("num").partition(".")[2]), _places_needed(new))
    return f"{new:.{places}f}{m.group('suffix')}"


def _format_money(quote: str, new: Decimal, *, places: int | None = None) -> str:
    m = _fullmatch(_MONEY, quote)
    original_places = len((m.group("cents") or ".")[1:])
    value = new / 1000 if m.group("k") else new
    if places is None:
        places = max(original_places, _places_needed(value))
    grouped = "," in m.group("num") or len(m.group("num")) < 4  # noqa: PLR2004 - "$999" could not show a comma
    body = f"{value:,.{places}f}" if grouped else f"{value:.{places}f}"
    return f"{m.group('prefix')}{body}{m.group('k') or ''}"


def _format_negative(quote: str, new: Decimal) -> str:
    m = _fullmatch(_NO_FEE, quote)
    if m.group("kind").lower() == "annual":
        return f"{_format_money('$0', new)} annual{m.group('rest')}{m.group('fee')}"
    out = f"{m.group('kind')}{m.group('rest')}{m.group('fee')} up to {new:.{_places_needed(new)}f}%"
    out = out.lower()
    return out[0].upper() + out[1:] if m.group("no")[0].isupper() else out


def _format(quote: str, new: Decimal) -> str:
    if _NO_FEE.fullmatch(quote):
        return quote if new == 0 else _format_negative(quote, new)
    if _PERCENT.fullmatch(quote):
        return _format_percent(quote, new)
    if _MONEY.fullmatch(quote):
        return _format_money(quote, new)
    return str(int(new))


def _new_term(old: int, offered: tuple[int, ...], role: str) -> int:
    if old in offered:
        return old
    if role == "min":
        return min(offered)
    if role == "max":
        return max(offered)
    return min(offered, key=lambda n: (abs(n - old), n))


def _new_value(ref: TermsRefDraft, terms: Terms, analysis: Analysis) -> Decimal | None:
    if ref.field == "term_months" and isinstance(terms, PersonalLoanTerms):
        role = next((c.role for c in analysis.claims if c.field == "term_months" and c.span == ref.span), "value")
        return Decimal(_new_term(int(ref.quoted_value), terms.term_months, role))
    value = getattr(terms, ref.field)
    return None if value is None else Decimal(value)


def _example_payment(example: Example, quote: str, new_values: dict[Span, Decimal]) -> str:
    amount = new_values.get(example.amount.span, example.amount.value)
    apr = new_values.get(example.apr.span, example.apr.value)
    months = example.term.months
    places = example.payment.decimals
    payment = monthly_payment(amount, apr, months).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
    return _format_money(quote, payment, places=places)


def _validate(text: str, refs: Sequence[TermsRefDraft], allowed: frozenset[str]) -> list[TermsRefDraft]:
    ordered = sorted(refs, key=lambda r: (r.span.start, r.span.end))
    for prev, cur in pairwise(ordered):
        if cur.span.start < prev.span.end:
            raise ValueError(f"refs overlap at [{cur.span.start}, {prev.span.end})")
    for ref in ordered:
        if ref.field not in allowed:
            raise ValueError(f"field {ref.field!r} is not a referenceable offer term for these terms")
        if ref.span.end > len(text):
            raise ValueError(f"ref span [{ref.span.start}, {ref.span.end}) is outside the text")
        quote = text[ref.span.start : ref.span.end]
        if _parse(quote) != ref.quoted_value:
            raise ValueError(f"text {quote!r} at the ref span doesn't match the quoted value {ref.quoted_value}")
    return ordered


def render_fast_track(text: str, refs: Sequence[TermsRefDraft], new_terms: PersonalLoanTerms | CreditCardTerms) -> str:
    ordered = _validate(text, refs, REFERENCEABLE[type(new_terms)])
    analysis = analyze(text, new_terms.product, new_terms)
    replacements: dict[Span, str] = {}
    new_values: dict[Span, Decimal] = {}
    for ref in ordered:
        if ref.field == "example_payment":
            continue
        new = _new_value(ref, new_terms, analysis)
        if new is None:
            continue
        new_values[ref.span] = new
        replacements[ref.span] = _format(text[ref.span.start : ref.span.end], new)
    examples = {e.payment.span: e for e in analysis.examples}
    for ref in ordered:
        if ref.field != "example_payment":
            continue
        example = examples.get(ref.span)
        if example is None:
            raise ValueError(f"no representative example around the payment at [{ref.span.start}, {ref.span.end})")
        replacements[ref.span] = _example_payment(example, text[ref.span.start : ref.span.end], new_values)
    out = text
    for span in sorted(replacements, key=lambda s: s.start, reverse=True):
        out = out[: span.start] + replacements[span] + out[span.end :]
    return out
