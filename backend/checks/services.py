"""Running checks and persisting their results. The only writer of Finding, TermsRef, and CheckRun."""

from dataclasses import dataclass
from typing import Self

from checks.engine import CheckResult
from core.clock import SYSTEM_CLOCK, Clock
from reviews.models import Version


@dataclass(frozen=True)
class PersistedChecks:
    """What `run_code_checks` stored for a version.

    `open_findings_count` is the count after carrying identical dismissals forward (ruling 4), so it can be
    lower than `len(result.findings)`. The caller writes it to `ReviewItem.open_findings_count`.
    """

    result: CheckResult
    open_findings_count: int

    @classmethod
    def empty(cls) -> Self:
        return cls(result=CheckResult(findings=(), terms_refs=()), open_findings_count=0)


def run_code_checks(*, version: Version, clock: Clock = SYSTEM_CLOCK) -> PersistedChecks:
    """Run the code rules on `version` synchronously and persist findings and terms refs.

    Seam (the C/E integration): build a `checks.engine.RuleContext` for the version (its item's product,
    channel, markets, partner type, attachment kinds, the current OfferTerms values, today), call
    `checks.engine.run_code_checks`, write Findings (`suggested_fix or ""`), TermsRefs (`TermsField(draft.field)`)
    and a CheckRun keyed by `checks.engine.ENGINE_VERSION`, carry forward identical dismissals (ruling 4), and
    record CHECKS_COMPLETED. Return the open count; the calling action (submit, resubmit) writes it to the item in
    the same transaction, so one action has one writer of `open_findings_count`. Until that lands this persists
    nothing and reports an empty result, so submission works end to end.
    """
    del version, clock
    return PersistedChecks.empty()
