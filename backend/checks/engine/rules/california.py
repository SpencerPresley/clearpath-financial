"""California Financing Law license disclosure (Cal. Fin. Code §22162).

The statute requires the printed text of an ad "disseminated primarily in this state for a loan" to disclose the
license the loan is made or arranged under, but prescribes no wording; accepted phrases come from EngineConfig.
Scoped to personal loans and mortgages: cards are issued by the sponsor bank, not made under a CFL license.
"""

import re
from collections.abc import Iterable
from functools import cache

from checks.engine.config import EngineConfig
from checks.engine.extract import Analysis
from checks.engine.rule import ADOPTED, CALIFORNIA, CLOSED_END, URL_CA_22162, Hit, Rule, make_spec
from checks.engine.text import phrase_pattern
from checks.engine.types import RuleContext
from core.domain import Severity

LICENSE_DISCLOSURE = make_spec(
    "ca.license_disclosure",
    title="California ads disclose the lending license",
    citation="Cal. Fin. Code §22162",
    url=URL_CA_22162,
    severity=Severity.BLOCKING,
    products=CLOSED_END,
    markets=CALIFORNIA,
    effective_from=ADOPTED,
)


@cache
def _phrases(phrases: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile("|".join(phrase_pattern(p) for p in phrases), re.IGNORECASE)


def _license_disclosure(_ctx: RuleContext, a: Analysis, config: EngineConfig) -> Iterable[Hit]:
    phrases = config.ca_license_phrases
    if not phrases or not _phrases(phrases).search(a.text):
        yield Hit(
            None,
            "Ads running in California must disclose the license the loan is made or arranged under.",
            f'"{phrases[0]}."' if phrases else None,
        )


RULES: tuple[Rule, ...] = (Rule(LICENSE_DISCLOSURE, _license_disclosure),)
