"""Running checks and persisting their results. The only writer of Finding, TermsRef, and CheckRun."""

from checks.contracts import CodeCheckResult
from core.clock import SYSTEM_CLOCK, Clock
from reviews.models import Version


def run_code_checks(*, version: Version, clock: Clock = SYSTEM_CLOCK) -> CodeCheckResult:
    """Run the code rules on `version` synchronously and persist findings and terms refs.

    Seam (workstreams C and E): build a `checks.contracts.CheckInput` for the version, run the rules engine
    (`checks.engine`), write Findings/TermsRefs/CheckRun, carry forward identical dismissals (ruling 4), set
    `ReviewItem.open_findings_count`, and record CHECKS_COMPLETED. Until the engine lands this persists
    nothing and reports an empty result, so submission works end to end with zero code findings.
    """
    del version, clock
    return CodeCheckResult.empty()
