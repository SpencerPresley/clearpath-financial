"""Approval and credit-impact claims (regs table rows 10 and 11)."""

from collections.abc import Iterable

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.rule import (
    ADOPTED,
    ALL_PRODUCTS,
    URL_PRIME_CHOICE,
    URL_SH24,
    Hit,
    Rule,
    make_spec,
)
from checks.engine.text import APOS, compile_i, window_after, window_before
from checks.engine.types import RuleContext, Span
from core.domain import AttachmentKind, Severity

PREAPPROVED = make_spec(
    "claims.preapproved",
    title="Pre-approval claims need a prescreened firm offer",
    citation="Reg N 12 CFR 1014.3(q); 12 U.S.C. 5536; CFPB v. Prime Choice Funding (2020)",
    url=URL_PRIME_CHOICE,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=ADOPTED,
)
GUARANTEED = make_spec(
    "claims.guaranteed",
    title="Approval can't be promised",
    citation="Reg N 12 CFR 1014.3(q); Reg Z 12 CFR 1026.24(a), 1026.16(a); 12 U.S.C. 5536",
    url=URL_PRIME_CHOICE,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=ADOPTED,
)
CREDIT_IMPACT = make_spec(
    "claims.credit_impact",
    title="Credit-check and credit-score claims need substantiation",
    citation="CFPB Supervisory Highlights Issue 24 §2.8.2; 12 U.S.C. 5536",
    url=URL_SH24,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=ADOPTED,
)

_PREAPPROVED = compile_i(
    rf"\bpre[-\s]?(?:approved|selected)\b|\byou(?:{APOS}ve|\s+have)\s+(?:already\s+)?(?:been\s+)?(?:approved|selected)\b"
    rf"|\byou(?:{APOS}re|\s+are)\s+(?:already\s+)?approved\b|\byou(?:{APOS}ve|\s+have)?\s+(?:already\s+)?qualif(?:y|ied)\b"
)
_GUARANTEE = compile_i(r"\bguarantee(?:d|s)?\b")
_CREDIT_IMPACT = compile_i(
    r"\bno\s+(?:hard\s+)?credit\s+checks?\b|\bwithout\s+a\s+(?:hard\s+)?credit\s+check\b"
    rf"|\b(?:won{APOS}t|will\s+not|doesn{APOS}t|does\s+not|never)\s+(?:affect|impact|hurt|harm|lower|ding)\s+"
    r"your\s+credit(?:\s+scores?)?\b"
    r"|\bno\s+(?:impact|effect)\s+(?:on|to)\s+your\s+credit(?:\s+scores?)?\b"
    r"|\bwithout\s+(?:affecting|impacting|hurting)\s+your\s+credit(?:\s+scores?)?\b"
)
_NEGATION = compile_i(rf"\b(?:not|no|never|isn{APOS}t|aren{APOS}t|can{APOS}?t|cannot|without)\b[^.!?]{{0,12}}$")
_ASKING = compile_i(r"\b(?:if|whether|see|check|find\s+out|how)\s+$")
_QUESTION_AFTER = compile_i(r"^[^.!]{0,20}\?")
_LOOKBACK = 24


def _negated(text: str, start: int) -> bool:
    return bool(_NEGATION.search(window_before(text, start, _LOOKBACK)))


def _preapproved(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if AttachmentKind.PRESCREEN_CRITERIA in ctx.attachment_kinds:
        return
    for m in _PREAPPROVED.finditer(a.text):
        before = window_before(a.text, m.start(), _LOOKBACK)
        if _negated(a.text, m.start()) or _ASKING.search(before):
            continue
        if "qualif" in m.group(0).lower() and _QUESTION_AFTER.match(window_after(a.text, m.end(), 24)):
            continue
        yield Hit(
            Span(m.start(), m.end()),
            "Pre-approval language implies a firm offer. Use it only for a prescreened offer with the selection "
            "criteria on file, or soften it.",
            'Attach the prescreen criteria, or say "See if you qualify."',
        )


def _guaranteed(_ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    for m in _GUARANTEE.finditer(a.text):
        if _negated(a.text, m.start()):
            continue
        yield Hit(
            Span(m.start(), m.end()),
            "Approval depends on underwriting, so a guarantee may mislead. Remove it or say approval isn't guaranteed.",
            '"Subject to credit approval."',
        )


def _credit_impact(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if AttachmentKind.SUBSTANTIATION in ctx.attachment_kinds:
        return
    for m in _CREDIT_IMPACT.finditer(a.text):
        yield Hit(
            Span(m.start(), m.end()),
            "Credit-impact claims need evidence of the pull type. Attach substantiation and limit the claim to the "
            "soft-pull step.",
            '"Checking your rate won\'t affect your credit score. Applying involves a hard credit inquiry."',
        )


RULES: tuple[Rule, ...] = (
    Rule(PREAPPROVED, _preapproved),
    Rule(GUARANTEED, _guaranteed),
    Rule(CREDIT_IMPACT, _credit_impact),
)
