"""Workflow refusals beyond `core.errors`. Each is a `Conflict` (409) with a stable code the frontend switches
on; `config.api` maps every DomainError subclass, so nothing here needs registering."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import JsonValue

from core.domain import FindingState
from core.errors import Conflict


class StaleVersion(Conflict):
    code = "stale_version"

    def __init__(self, *, version_n: int, current_n: int | None) -> None:
        super().__init__(
            f"v{version_n} isn't the current version (v{current_n}). Reload the item.",
            details={"version_n": version_n, "current_n": current_n},
        )


class AcceptedFindingsBlockApproval(Conflict):
    """Accepted findings are required changes; the approved version is exactly what goes live."""

    code = "accepted_findings_block_approval"

    def __init__(self, *, accepted_count: int) -> None:
        noun = "finding is" if accepted_count == 1 else "findings are"
        super().__init__(
            f"{accepted_count} accepted {noun} a required change. Approve with edits or request changes.",
            details={"accepted_count": accepted_count},
        )


@dataclass(frozen=True)
class FindingSummary:
    id: int
    rule_id: str
    severity: str
    source: str
    message: str
    quote: str | None

    def as_json(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "source": self.source,
            "message": self.message,
            "quote": self.quote,
        }


class FindingsNeedTriage(Conflict):
    """The version to approve has findings nobody has looked at yet: a reviewer's edit (v+1) or a reaffirm's
    re-check raised them. They are saved; triage them and approve again."""

    code = "findings_need_triage"

    def __init__(self, *, version_n: int, findings: Sequence[FindingSummary]) -> None:
        noun = "finding" if len(findings) == 1 else "findings"
        super().__init__(
            f"v{version_n} has {len(findings)} new {noun}. Triage them, then approve again.",
            details={"version_n": version_n, "findings": [f.as_json() for f in findings]},
        )


class StaleOfferTerms(Conflict):
    """The copy quotes an offer-terms version that is no longer in effect."""

    code = "stale_offer_terms"

    def __init__(self, *, versions: Sequence[str]) -> None:
        listed = ", ".join(versions)
        super().__init__(
            f"This version quotes offer terms no longer in effect ({listed}). Request changes or edit the rates.",
            details={"terms_versions": list(versions)},
        )


class FindingStateConflict(Conflict):
    code = "invalid_finding_transition"

    def __init__(self, *, action: str, state: FindingState) -> None:
        super().__init__(f"Can't {action} a finding that is {state}.", details={"action": action, "state": str(state)})
