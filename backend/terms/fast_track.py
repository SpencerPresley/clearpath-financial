"""Fast-track approval of generated terms-change versions (spec §4.2 ruling 4; decisions.md "Rates are stored once").

Thin over E's decision service: `record_decision(lane=FAST_TRACK)` applies every approval gate (current version,
current offer terms, no open or accepted findings; the AI check is skipped on generated versions) and records "AI
review carried from vN". Bulk runs one item per transaction through `run_bulk`, so an item with open findings comes
back as a skip (`open_findings_block_decision`) and goes to the normal lane; the others are approved.
"""

from collections.abc import Iterable, Mapping

from accounts.models import User
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import DecisionLane, DecisionOutcome
from core.errors import NotFound
from core.permissions import REVIEW_ROLES, require_role
from reviews.assignment import BulkResult, run_bulk
from reviews.decisions import DecisionInput, DecisionResult, record_decision
from reviews.models import ReviewItem


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


def _current_n(item_id: int) -> int:
    row = ReviewItem.objects.filter(pk=item_id).values_list("current_version__n", flat=True).first()
    if row is None:
        if not ReviewItem.objects.filter(pk=item_id).exists():
            raise NotFound.entity("item", item_id)
        return 0  # no version at all (legacy): record_decision answers stale_version
    return row


def bulk_fast_track_approve(
    *,
    actor: User,
    item_ids: Iterable[int],
    reason: str,
    seen_versions: Mapping[int, int] | None = None,
    clock: Clock = SYSTEM_CLOCK,
) -> BulkResult:
    """Reviewers and leads. Each item is the single fast-track in its own transaction, with the same per-item check
    (the item's assignee or a lead), so a reviewer's bulk approve covers only their own items and the rest come back
    as `not_permitted` skips. Anything that can't be fast-tracked is a skip with its error code, never an exception.

    `seen_versions` maps an item to the version the reviewer saw; that item is approved only at that version (else
    `stale_version`). An item without an entry is approved at its current version.
    """
    require_role(actor, *REVIEW_ROLES)
    seen = dict(seen_versions or {})
    return run_bulk(
        item_ids,
        lambda item_id: fast_track_approve(
            actor=actor,
            item_id=item_id,
            version_n=seen[item_id] if item_id in seen else _current_n(item_id),
            reason=reason,
            clock=clock,
        ),
    )
