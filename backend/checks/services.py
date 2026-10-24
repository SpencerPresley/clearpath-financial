"""Running checks and persisting their results. The only writer of Finding, TermsRef, and CheckRun."""

from dataclasses import dataclass
from typing import Self

from checks.contracts import CodeCheckResult
from core.clock import SYSTEM_CLOCK, Clock
from reviews.models import Version


@dataclass(frozen=True)
class PersistedChecks:
    """What `run_code_checks` stored for a version.

    `open_findings_count` is the count after carrying identical dismissals forward (ruling 4), so it can be
    lower than `len(result.findings)`. The caller writes it to `ReviewItem.open_findings_count`.
    """

    result: CodeCheckResult
    open_findings_count: int

    @classmethod
    def empty(cls) -> Self:
        return cls(result=CodeCheckResult.empty(), open_findings_count=0)


def run_code_checks(*, version: Version, clock: Clock = SYSTEM_CLOCK) -> PersistedChecks:
    """Run the code rules on `version` synchronously and persist findings and terms refs.

    Seam (workstreams C and E): build a `checks.contracts.CheckInput` for the version, run the rules engine
    (`checks.engine`), write Findings/TermsRefs/CheckRun, carry forward identical dismissals (ruling 4), and
    record CHECKS_COMPLETED. Return the open count; the calling action (submit, resubmit) writes it to the
    item in the same transaction, so one action has one writer of `open_findings_count`. Until the engine
    lands this persists nothing and reports an empty result, so submission works end to end.
    """
    del version, clock
    return PersistedChecks.empty()
