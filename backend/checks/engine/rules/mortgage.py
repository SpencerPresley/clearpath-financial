"""Mortgage advertising: ARM "fixed", taxes-and-insurance payment statement, banned phrases.

Regs table rows 7 (ARM part), 8 and 9; Reg Z 1026.24(f), (i); Reg N 1014.3. ClearPath is a nonbank and not
FHA-approved (decisions.md, Company facts), so any government-affiliation claim is flagged.
"""

import re
from collections.abc import Iterable

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.rule import REGN_1014, REGZ_1026_24, URL_1014, URL_1026_24, Hit, Rule, make_spec
from checks.engine.text import APOS, compile_i, window_after, window_before
from checks.engine.types import RuleContext, Span
from core.domain import Product, Severity

MORTGAGE = frozenset({Product.MORTGAGE_PREQUAL})

ARM_FIXED = make_spec(
    "mortgage.arm_fixed",
    title='"Fixed" in an ARM ad follows the ARM name and states the fixed period',
    citation="Reg Z 12 CFR 1026.24(i)(1); Reg N 12 CFR 1014.3(g)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=MORTGAGE,
    effective_from=REGZ_1026_24,
)
PAYMENT_TAXES_INSURANCE = make_spec(
    "mortgage.payment_taxes_insurance",
    title="Payment amounts say taxes and insurance aren't included",
    citation="Reg Z 12 CFR 1026.24(f)(3)(i)(C), (f)(3)(ii), comment 24(f)-2",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=MORTGAGE,
    effective_from=REGZ_1026_24,
)
GOVERNMENT = make_spec(
    "mortgage.government",
    title="No implied government affiliation",
    citation="Reg Z 12 CFR 1026.24(i)(3); Reg N 12 CFR 1014.3(n)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=MORTGAGE,
    effective_from=REGZ_1026_24,
)
DEBT_ELIMINATION = make_spec(
    "mortgage.debt_elimination",
    title="No debt-elimination claims",
    citation="Reg Z 12 CFR 1026.24(i)(5), comment 24(i)-3; Reg N 12 CFR 1014.3(m)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=MORTGAGE,
    effective_from=REGZ_1026_24,
)
COUNSELOR = make_spec(
    "mortgage.counselor",
    title='No "counselor" for loan staff',
    citation="Reg Z 12 CFR 1026.24(i)(6); Reg N 12 CFR 1014.3(s)",
    url=URL_1026_24,
    severity=Severity.BLOCKING,
    products=MORTGAGE,
    effective_from=REGZ_1026_24,
)
PREAPPROVAL_OFFER = make_spec(
    "mortgage.preapproval_offer",
    title="Mortgage ads offer prequalification, not preapproval",
    citation="Reg N 12 CFR 1014.3(q), (i); 12 U.S.C. 5536",
    url=URL_1014,
    severity=Severity.WARNING,
    products=MORTGAGE,
    effective_from=REGN_1014,
)

# ClearPath's mortgage product is prequalification; preapproval is a different, underwritten product, so inviting
# a "pre-approval" can misdescribe what's offered (coordinator ruling, docs/plan/ledger.md). Assertions that the
# reader *is* pre-approved are claims.preapproved (blocking); this catches the invitation and the noun.
_PREAPPROVAL_OFFER = compile_i(r"\b(?:get|getting|be|become)\s+pre[-\s]?approved\b|\bpre[-\s]?approvals?\b")

# "ARM" is matched case-sensitively ("arm" is an ordinary word); everything else ignores case.
_ARM_CONTEXT = re.compile(r"\bARM\b|(?i:\b(?:adjustable|variable)[-\s]rate\b|\brate\s+(?:may\s+)?adjusts?\b)")
_ARM_NAME = re.compile(r"\bARM\b|(?i:\b(?:adjustable|variable)[-\s]rate\s+mortgage\b)")
_FIXED = compile_i(r"\bfixed\b")
# "fixed" naming a fixed-rate product in an ad that offers both kinds (1026.24(i)(1)(iii)): "30-year fixed".
_FIXED_PRODUCT = compile_i(r"\b\d{1,2}[-\s]year\s+fixed\b|\bfixed[-\s]rate\s+(?:mortgages?|loans?|options?)\b")
_ARM_TYPE = re.compile(r"\b(\d{1,2})/\d{1,2}(?:\s+ARM\b|(?i:\s+adjustable[-\s]rate\s+mortgage\b))")
_FIXED_PERIOD = compile_i(r"\b\d+\s*(?:-\s*)?(?:years?|yrs?|months?)\b")
_MAY_CHANGE = compile_i(
    r"\b(?:may|can|could|will|then)\s+(?:\w+\s+)?(?:adjust|change|vary|increase|reset)\w*|\badjusts?\b|\badjustable\b"
)
_FIXED_REACH = 120

_TAXES_EXCLUDED = compile_i(
    rf"\b(?:do(?:es)?\s+not\s+include|don{APOS}t\s+include|doesn{APOS}t\s+include|exclud(?:e|es|ing)|not\s+"
    r"including)\b[^.]{0,60}?\btaxes\b[^.]{0,40}?\binsurance\b"
)
_GREATER = compile_i(
    r"\b(?:actual|total)\s+(?:monthly\s+)?payments?(?:\s+obligations?)?\s+will\s+be\s+(?:greater|higher)\b"
)

_GOVERNMENT = re.compile(
    r"\bgovernment(?:[-\s](?:loans?|programs?|backed|supported|sponsored|insured|guaranteed|assisted))+\b"
    r"|\bfederal(?:ly)?[-\s](?:backed|insured|guaranteed|loan\s+programs?|programs?)\b",
    re.IGNORECASE,
)
_AGENCIES = re.compile(
    r"\b(?:FHA|HUD|USDA)\b|\bVA(?:[-\s](?:loans?|mortgages?|home\s+loans?|backed|guaranteed|programs?|benefits?))\b"
)
_DEBT_ELIMINATION = compile_i(
    r"\bwipe[-\s]?out\b[^.!?]{0,30}?\bdebts?\b|\bwipe\s+(?:\w+\s+){0,2}debts?\b|\bdebt[-\s]free\b"
    r"|\bget\s+(?:yourself\s+)?out\s+of\s+debt\b|\bset\s+yourself\s+free\b|\b(?:eliminate|erase)\s+(?:\w+\s+){0,2}"
    r"debts?\b|\bdebt\s+(?:forgiveness|elimination)\b|\bpre-?payment\s+penalty\s+waiver\b"
)
_COUNSELOR = compile_i(r"\bcounsell?ors?\b")
_DISCLAIMER = compile_i(r"\b(?:not|no|never|nor)\b[^.!?;]{0,40}$")
_HOUSING_COUNSELING = compile_i(r"HUD[-\s]approved\s+(?:housing\s+)?counsel|\bhousing\s+counsell?ors?\b")
_DISCLAIMER_REACH = 48


def _arm_fixed(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    text = a.text
    if not _ARM_CONTEXT.search(text):
        return
    products = [Span(m.start(), m.end()) for m in _FIXED_PRODUCT.finditer(text)]
    fixed = [m for m in _FIXED.finditer(text) if not any(p.start <= m.start() < p.end for p in products)]
    if not fixed:
        return
    first = fixed[0]
    # The fixed period comes from the ARM the copy names ("7/6 ARM" is fixed 7 years); there are no mortgage rate
    # terms to take it from, so without one the suggestion leaves the number out rather than inventing it.
    arm = _ARM_TYPE.search(text)
    years = arm.group(1) if arm else None
    if not _ARM_NAME.search(text, 0, first.start()):
        yield Hit(
            Span(first.start(), first.end()),
            'In an adjustable-rate ad, put "ARM" or "Adjustable-Rate Mortgage" before the first "fixed", '
            "at least as prominently.",
            f'"{arm.group(0)}: rate fixed for the first {years} years, then may adjust"' if arm else None,
        )
        return
    for m in fixed:
        para = a.segments.paragraph(m.start())
        near = window_before(text, m.start(), _FIXED_REACH, para.start) + window_after(
            text, m.end(), _FIXED_REACH, para.end
        )
        if not (_FIXED_PERIOD.search(near) and _MAY_CHANGE.search(near)):
            yield Hit(
                Span(m.start(), m.end()),
                'Next to each "fixed", say how long the rate is fixed and that it may change after that.',
                f'"fixed for the first {years} years, then may adjust"' if years else None,
            )


def _payment_taxes_insurance(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    payment = next((m for m in a.moneys if m.role == "payment"), None)
    if payment is None:
        return
    para = a.segments.paragraph(payment.span.start)
    if _TAXES_EXCLUDED.search(a.text, para.start, para.end) and _GREATER.search(a.text, para.start, para.end):
        return
    elsewhere = _TAXES_EXCLUDED.search(a.text) and _GREATER.search(a.text)
    message = (
        "Move the taxes-and-insurance statement next to the payment; a footnote doesn't count."
        if elsewhere
        else "Add next to the payment that it excludes taxes and insurance and the actual payment will be greater."
    )
    yield Hit(
        payment.span,
        message,
        '"Payment does not include taxes and insurance premiums; the actual payment obligation will be greater."',
    )


def _government(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    matches = sorted([*_GOVERNMENT.finditer(a.text), *_AGENCIES.finditer(a.text)], key=lambda m: m.start())
    for m in matches:
        sentence = a.segments.sentence(m.start())
        before = window_before(a.text, m.start(), _DISCLAIMER_REACH, sentence.start)
        if _DISCLAIMER.search(before) or _HOUSING_COUNSELING.match(a.text, m.start()):
            continue  # "not affiliated with HUD", "a HUD-approved housing counselor"
        yield Hit(
            Span(m.start(), m.end()),
            "ClearPath isn't a government program or FHA-approved; remove language implying government backing.",
            None,
        )


def _debt_elimination(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for m in _DEBT_ELIMINATION.finditer(a.text):
        yield Hit(
            Span(m.start(), m.end()),
            "Debt-elimination language may mislead. It's fine to say the loan can consolidate or reduce payments.",
            '"Consolidate your debt into one monthly payment."',
        )


def _counselor(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for m in _COUNSELOR.finditer(a.text):
        if _HOUSING_COUNSELING.search(window_before(a.text, m.end(), _DISCLAIMER_REACH)):
            continue  # referring consumers to housing counseling is not calling loan staff counselors
        span = Span(m.start(), m.end())
        yield Hit(span, 'Call loan staff "loan officers," not "counselors."', '"loan officer"')
        return


def _preapproval_offer(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for m in _PREAPPROVAL_OFFER.finditer(a.text):
        yield Hit(Span(m.start(), m.end()), "ClearPath offers prequalification, not preapproval.", '"Get prequalified"')


RULES: tuple[Rule, ...] = (
    Rule(ARM_FIXED, _arm_fixed),
    Rule(PAYMENT_TAXES_INSURANCE, _payment_taxes_insurance),
    Rule(GOVERNMENT, _government),
    Rule(DEBT_ELIMINATION, _debt_elimination),
    Rule(COUNSELOR, _counselor),
    Rule(PREAPPROVAL_OFFER, _preapproval_offer),
)
