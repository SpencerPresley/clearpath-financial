"""Prescreened firm offers: criteria on file and both FCRA notices present in the text (regs table rows 10, 12).

Layout (type size, border, placement) is a human checklist item; the text checks here only establish that the
notices exist.
"""

import re
from collections.abc import Iterable

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.rule import (
    ALL_PRODUCTS,
    REGB_1002_12,
    REGV_1022_54,
    URL_1002_12,
    URL_1022_54,
    Hit,
    Rule,
    instruct,
    make_spec,
)
from checks.engine.text import QUOTE_CLOSE, QUOTE_OPEN, compile_i, first_span
from checks.engine.types import RuleContext
from core.domain import AttachmentKind, Severity

CRITERIA_ON_FILE = make_spec(
    "prescreen.criteria_on_file",
    title="Prescreened offers need the selection criteria on file",
    citation="FCRA 15 U.S.C. 1681m(d)(3); Reg B 12 CFR 1002.12(b)(7)",
    url=URL_1002_12,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=REGB_1002_12,
)
SHORT_NOTICE = make_spec(
    "prescreen.short_notice",
    title="Prescreened offers need the short opt-out notice",
    citation="Reg V 12 CFR 1022.54(c)(1)",
    url=URL_1022_54,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=REGV_1022_54,
)
LONG_NOTICE = make_spec(
    "prescreen.long_notice",
    title='Prescreened offers need the long notice headed "PRESCREEN & OPT-OUT NOTICE"',
    citation="Reg V 12 CFR 1022.54(c)(2)",
    url=URL_1022_54,
    severity=Severity.BLOCKING,
    products=ALL_PRODUCTS,
    effective_from=REGV_1022_54,
)

_HEADING = r"PRESCREEN\s*&\s*OPT-OUT\s+NOTICE"
_PRESCREEN_WORDING = compile_i(rf"\bpre-?screen(?:ed|ing)?\b|{_HEADING}|1-888-5-?OPT-?OUT|1-888-567-8688")
_SHORT_OPT_OUT = compile_i(
    rf"\b(?:stop|opt\s+out\s+of)\s+receiving\s+{QUOTE_OPEN}pre-?screened{QUOTE_CLOSE}\s+offers\b"
)
_TOLL_FREE = compile_i(r"\b1-?8(?:00|88|77|66|55|44|33)-?(?:\d{3}-?\d{4}|5-?OPT-?OUT)\b")
_HEADING_REFERENCE = re.compile(rf"\bSee\s+{_HEADING}", re.IGNORECASE)
_HEADING_CAPS = re.compile(_HEADING)  # case-sensitive: the heading must be in capitals
_HEADING_LINE = re.compile(rf"^[ \t\u00a0]*{_HEADING}[ \t\u00a0]*$", re.MULTILINE)
_SHORT_NOTICE_REACH = 400


def is_prescreen(ctx: RuleContext) -> bool:
    return AttachmentKind.PRESCREEN_CRITERIA in ctx.attachment_kinds or bool(_PRESCREEN_WORDING.search(ctx.text))


def _has_short_notice(a: Analysis) -> bool:
    """Opt-out statement, toll-free number and a reference to the long notice, all in one paragraph."""
    text = a.text
    for m in _SHORT_OPT_OUT.finditer(text):
        para = a.segments.paragraph(m.start())
        lo = max(para.start, m.start() - _SHORT_NOTICE_REACH)
        hi = min(para.end, m.end() + _SHORT_NOTICE_REACH)
        reference = _HEADING_REFERENCE.search(text, lo, hi)
        if _TOLL_FREE.search(text, lo, hi) and reference and _HEADING_CAPS.search(reference.group(0)):
            return True
    return False


def _criteria_on_file(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if AttachmentKind.PRESCREEN_CRITERIA in ctx.attachment_kinds:
        return
    if span := first_span(_PRESCREEN_WORDING, a.text):
        yield instruct(
            span,
            "This reads as a prescreened offer. Attach the selection criteria, which must be kept with the offer.",
            "Attach the prescreen criteria (kind: prescreen_criteria).",
        )


def _short_notice(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if is_prescreen(ctx) and not _has_short_notice(a):
        yield instruct(
            None,
            "Add the short prescreen notice: the opt-out right, the toll-free number, and where to find the "
            '"PRESCREEN & OPT-OUT NOTICE".',
            'You can choose to stop receiving "prescreened" offers of credit from this and other companies by calling '
            "toll-free 1-888-5-OPT-OUT (1-888-567-8688). See PRESCREEN & OPT-OUT NOTICE below for more information.",
        )


def _long_notice(ctx: RuleContext, a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if is_prescreen(ctx) and not _HEADING_LINE.search(a.text):
        yield instruct(
            None,
            'Add the long prescreen notice under its own heading line, "PRESCREEN & OPT-OUT NOTICE", in capitals.',
            "PRESCREEN & OPT-OUT NOTICE",
        )


RULES: tuple[Rule, ...] = (
    Rule(CRITERIA_ON_FILE, _criteria_on_file),
    Rule(SHORT_NOTICE, _short_notice),
    Rule(LONG_NOTICE, _long_notice),
)
