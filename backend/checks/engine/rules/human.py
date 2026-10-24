"""Human checklist items: things a reviewer must look at that text matching cannot settle (spec §4.2 ruling 7).

They are findings with source=human and no span; `run_code_checks` never emits them.
"""

from collections.abc import Iterable

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.rule import (
    ALL_PRODUCTS,
    REGB_1002_4,
    REGN_1014,
    REGV_1022_54,
    TCPA_64_1200,
    URL_64_1200,
    URL_1002_4,
    URL_1022_54,
    URL_1026_24,
    Hit,
    Rule,
    make_spec,
)
from checks.engine.rules.prescreen import is_prescreen
from checks.engine.types import RuleContext
from core.domain import Channel, Product, Severity

REG_B = make_spec(
    "human.reg_b_discouragement",
    title="Imagery and targeting don't discourage applicants on a prohibited basis",
    citation="Reg B 12 CFR 1002.4(b) (text effective 2026-07-21)",
    url=URL_1002_4,
    severity=Severity.WARNING,
    products=ALL_PRODUCTS,
    effective_from=REGB_1002_4,
    kind="human",
)
PRESCREEN_FORMAT = make_spec(
    "human.prescreen_format",
    title="Prescreen notices meet type size, placement and layout rules",
    citation="Reg V 12 CFR 1022.54(c)",
    url=URL_1022_54,
    severity=Severity.WARNING,
    products=ALL_PRODUCTS,
    effective_from=REGV_1022_54,
    kind="human",
)
GOVERNMENT_IMAGERY = make_spec(
    "human.government_imagery",
    title="No government seals, eagles or look-alike logos in the creative",
    citation="Reg Z 12 CFR 1026.24(i)(3); Reg N 12 CFR 1014.3(n)",
    url=URL_1026_24,
    severity=Severity.WARNING,
    products=frozenset({Product.MORTGAGE_PREQUAL}),
    effective_from=REGN_1014,
    kind="human",
)
SMS_SEND_WINDOW = make_spec(
    "human.sms_send_window",
    title="Texts are scheduled between 8 a.m. and 9 p.m. recipient local time",
    citation="TCPA 47 CFR 64.1200(c)(1)",
    url=URL_64_1200,
    severity=Severity.WARNING,
    products=ALL_PRODUCTS,
    channels=frozenset({Channel.SMS}),
    effective_from=TCPA_64_1200,
    kind="human",
)


def _reg_b(_ctx: RuleContext, _a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    yield Hit(
        None,
        "Check the people shown, the imagery and any geographic targeting for anything that could discourage "
        "applicants on a prohibited basis.",
    )


def _prescreen_format(ctx: RuleContext, _a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    if is_prescreen(ctx):
        yield Hit(
            None,
            "Check the prescreen notices' layout: short notice on the front page, bordered, larger than body text "
            "and at least 12-point; long notice at least 8-point, set apart, heading in capitals and underlined.",
        )


def _government_imagery(_ctx: RuleContext, _a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    yield Hit(None, "Check the creative for government seals, eagles, flags used as seals, or agency look-alike logos.")


def _sms_send_window(_ctx: RuleContext, _a: Analysis, _c: EngineConfig) -> Iterable[Hit]:
    yield Hit(None, "Confirm the send schedule stays within 8 a.m. to 9 p.m. in each recipient's local time.")


RULES: tuple[Rule, ...] = (
    Rule(REG_B, _reg_b),
    Rule(PRESCREEN_FORMAT, _prescreen_format),
    Rule(GOVERNMENT_IMAGERY, _government_imagery),
    Rule(SMS_SEND_WINDOW, _sms_send_window),
)
