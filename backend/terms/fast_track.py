"""Fast-track approval of generated terms-change versions (spec §4.2 ruling 4; decisions.md "Rates are stored once").

Thin over E's decision service: `record_decision(lane=FAST_TRACK)` applies every approval gate (current version,
current offer terms, no open or accepted findings, and no live page that differs from the approved copy,
`drift_not_restored`; the AI check is skipped on generated versions) and records "AI
review carried from vN". The single approve is the assignee's or a lead's and names the version on screen. Bulk is a
lead's (product-spec Roles: bulk actions are Lead) and runs one item per transaction through `run_bulk`, so an item
with open findings comes back as a skip (`open_findings_block_decision`) and goes to the normal lane; the others are
approved.
"""

from collections.abc import Iterable, Mapping
from typing import Final

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import DecisionLane, DecisionOutcome, Role
from core.errors import InvalidInput
from core.permissions import require_role
from reviews.assignment import BulkResult, run_bulk
from reviews.decisions import DecisionInput, DecisionResult, record_decision

_NAMED: Final = 5  # items named in the missing-seen-version message


def fast_track_approve(
    *, actor: User, item_id: int, version_n: int, reason: str, clock: Clock = SYSTEM_CLOCK
) -> DecisionResult:
    """needs_rereview -> approved on the generated version `version_n` (the one the reviewer looked at; anything
    else is `stale_version`). The item's assignee or a lead."""
    return record_decision(
        actor=actor,
        item_id=item_id,
        data=DecisionInput(
            outcome=DecisionOutcome.APPROVED, version_n=version_n, reason=reason, lane=DecisionLane.FAST_TRACK
        ),
        clock=clock,
    )


def bulk_fast_track_approve(
    *,
    actor: User,
    item_ids: Iterable[int],
    reason: str,
    seen_versions: Mapping[int, int],
    clock: Clock = SYSTEM_CLOCK,
) -> BulkResult:
    """Leads only. Each item is the single fast-track in its own transaction, with its checks. Anything that can't be
    fast-tracked is a skip with its error code, never an exception.

    `seen_versions` maps each item to the version the lead saw; the item is approved only at that version (else
    `stale_version`). Every item needs an entry (else InvalidInput, and nothing is approved): approving "whatever is
    current" could record a decision on a version a later terms change generated after the page loaded.
    """
    require_role(actor, Role.LEAD)
    ids = list(dict.fromkeys(item_ids))
    missing = [item_id for item_id in ids if item_id not in seen_versions]
    if missing:
        more = f" and {len(missing) - _NAMED} more" if len(missing) > _NAMED else ""
        keys = ", ".join(f"CP-{item_id}" for item_id in missing[:_NAMED]) + more
        raise InvalidInput.for_field("seen_versions", f"Send the version you saw for every item; missing for {keys}.")
    return run_bulk(
        ids,
        lambda item_id: fast_track_approve(
            actor=actor, item_id=item_id, version_n=seen_versions[item_id], reason=reason, clock=clock
        ),
    )
