"""Reviewer assignment (decisions.md "Reviewer assignment"): automatic, with claiming and overrides.

Automatic assignment takes the first rule that applies:
1. sticky: a resubmission or re-review goes back to the previous reviewer, if they're still available;
2. lowest weighted open load (high 3, medium 2, low 1) among available reviewers; ties go to whoever has gone
   longest without a new assignment;
3. nobody eligible: the unassigned pool, and the leads are notified (the ITEM_ASSIGNED handler does that).

Every write of `ReviewItem.assignee` happens here, under `pg_advisory_xact_lock(ASSIGNMENT_LOCK_KEY)`, and load
is computed after the lock is granted. Under READ COMMITTED each statement takes a fresh snapshot, so the load
query sees the assignment the previous lock holder just committed. Lock order: the item's row lock first, then
the advisory lock; a transaction never locks another item after taking it.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from django.db import connection, transaction
from django.db.models import Case, IntegerField, Sum, Value, When

from accounts.models import User
from audit.payloads import ItemAssignedPayload
from audit.services import record_event
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import AssignmentMode, EntityType, EventType, ItemStatus, RiskTier, Role
from core.errors import DomainError, InvalidInput, InvalidTransition, NotFound, NotPermitted
from core.permissions import REVIEW_ROLES, has_role, require_role
from reviews.models import QUEUE_STATUSES, Decision, ReviewItem
from reviews.transitions import start_review

# Any constant works; it only has to be the same in every process. "CPassign" as a big-endian int.
ASSIGNMENT_LOCK_KEY: Final = 0x4350_6173_7369_676E

TIER_WEIGHT: Final = {RiskTier.HIGH: 3, RiskTier.MEDIUM: 2, RiskTier.LOW: 1}

# Statuses whose assignee can be changed: where a reviewer still has work to do on the item.
ASSIGNABLE: Final = frozenset({*map(ItemStatus, QUEUE_STATUSES), ItemStatus.CHANGES_REQUESTED})
CLAIMABLE: Final = frozenset(map(ItemStatus, QUEUE_STATUSES))

_LONG_AGO: Final = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Assignment:
    assignee_id: int | None
    mode: AssignmentMode
    reason: str


def _name(user: User) -> str:
    return user.display_name or user.email


def _acquire_lock() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ASSIGNMENT_LOCK_KEY])


def locked_item(item_id: int) -> ReviewItem:
    item = ReviewItem.objects.select_for_update().filter(pk=item_id).first()
    if item is None:
        raise NotFound.entity("item", item_id)
    return item


def _set_assignee(  # the event's fields
    item: ReviewItem,
    user: User | None,
    *,
    actor: User | None,
    mode: AssignmentMode,
    reason: str,
    at: datetime,
    reopen_event_id: int | None = None,
) -> Assignment:
    previous = item.assignee_id  # pyrefly: ignore[missing-attribute]
    item.assignee = user
    item.assigned_at = at if user is not None else None
    item.updated_at = at
    item.save(update_fields=["assignee", "assigned_at", "updated_at"])
    if user is not None:
        User.objects.filter(pk=user.pk).update(last_assigned_at=at)
    record_event(
        type=EventType.ITEM_ASSIGNED,
        entity=EntityType.ITEM,
        entity_id=item.pk,
        item_id=item.pk,
        payload=ItemAssignedPayload(
            assignee_id=user.pk if user is not None else None,
            previous_assignee_id=previous,
            mode=mode,
            reason=reason,
            reopen_event_id=reopen_event_id,
        ),
        actor=actor,
        at=at,
    )
    return Assignment(assignee_id=user.pk if user is not None else None, mode=mode, reason=reason)


def _loads(user_ids: Iterable[int], *, excluding_item_id: int) -> dict[int, int]:
    weight = Case(
        *(When(risk_tier=tier.value, then=Value(w)) for tier, w in TIER_WEIGHT.items()),
        default=Value(1),
        output_field=IntegerField(),
    )
    rows = (
        ReviewItem.objects.filter(assignee_id__in=list(user_ids), status__in=QUEUE_STATUSES)
        .exclude(pk=excluding_item_id)
        .values("assignee_id")
        .annotate(load=Sum(weight))
        .values_list("assignee_id", "load")
    )
    return {uid: int(load) for uid, load in rows}


def _previous_reviewer(item: ReviewItem) -> User | None:
    """Who it goes back to: its current assignee (which respects a lead's manual reassignment while the item sat
    with the marketer), else the approver of its latest decision (e.g. after the assignee was unassigned)."""
    if item.assignee is not None:
        return item.assignee
    decision = Decision.objects.filter(item=item).select_related("approver").order_by("-decided_at", "-pk").first()
    return decision.approver if decision is not None else None


def _can_review(user: User, item: ReviewItem) -> bool:
    return user.is_available and has_role(user, *REVIEW_ROLES) and user.pk != item.owner_id  # pyrefly: ignore[missing-attribute]


def auto_assign(
    *,
    item: ReviewItem,
    actor: User | None,
    clock: Clock = SYSTEM_CLOCK,
    sticky: bool = False,
    reopen_event_id: int | None = None,
) -> Assignment:
    """Assign `item` (locked or freshly created by the caller) by the three rules, recording ITEM_ASSIGNED with
    the reason. `sticky` for resubmissions, new rounds, and re-reviews; a re-review also passes its ITEM_REOPENED
    (`reopen_event_id`), which the event records so the re-review notifies once.

    The sticky reviewer must still be active, available, a reviewer (a lead who reviewed counts), and not the
    item's owner; otherwise the item falls through to lowest load. The lowest-load pool uses stored roles, so a
    lead isn't auto-assigned new work unless also granted `reviewer` (Foundation, core.permissions).
    """
    _acquire_lock()
    now = clock.now()
    unavailable = ""
    if sticky:
        previous = _previous_reviewer(item)
        if previous is not None:
            previous.refresh_from_db(fields=["is_active", "is_available", "roles"])
            if _can_review(previous, item):
                return _set_assignee(
                    item,
                    previous,
                    actor=actor,
                    mode=AssignmentMode.STICKY,
                    reason=f"Back to {_name(previous)}, who reviewed it before",
                    at=now,
                    reopen_event_id=reopen_event_id,
                )
            unavailable = f"{_name(previous)} is unavailable. "
    pool = list(
        User.objects.filter(is_active=True, is_available=True, roles__contains=[Role.REVIEWER.value]).exclude(
            pk=item.owner_id  # pyrefly: ignore[missing-attribute]
        )
    )
    if not pool:
        return _set_assignee(
            item,
            None,
            actor=actor,
            mode=AssignmentMode.POOL,
            reason=f"{unavailable}No reviewer is available",
            at=now,
            reopen_event_id=reopen_event_id,
        )
    loads = _loads((u.pk for u in pool), excluding_item_id=item.pk)
    ranked = sorted(pool, key=lambda u: (loads.get(u.pk, 0), u.last_assigned_at or _LONG_AGO, u.pk))
    winner = ranked[0]
    reason = f"{_name(winner)}: load {loads.get(winner.pk, 0)}"
    if len(ranked) > 1:
        runner_up = ranked[1]
        reason += f" vs {_name(runner_up)} {loads.get(runner_up.pk, 0)}"
    return _set_assignee(
        item,
        winner,
        actor=actor,
        mode=AssignmentMode.LOWEST_LOAD,
        reason=f"{unavailable}{reason}",
        at=now,
        reopen_event_id=reopen_event_id,
    )


# --- claim, manual, hand-off, bulk -----------------------------------------------------------------------------


def require_reviewer_of(actor: User, item: ReviewItem) -> None:
    """Review actions on an item: its assignee or a lead, never its owner (no self-review)."""
    require_role(actor, *REVIEW_ROLES)
    if item.owner_id == actor.pk:  # pyrefly: ignore[missing-attribute]
        raise NotPermitted("You can't review your own submission.")
    if item.assignee_id != actor.pk and not has_role(actor, Role.LEAD):  # pyrefly: ignore[missing-attribute]
        holder = f"{_name(item.assignee)} has" if item.assignee is not None else "Nobody has"
        raise NotPermitted(f"{holder} this item. Claim it, or ask a lead to reassign it.")


def claim_item(*, actor: User, item_id: int, clock: Clock = SYSTEM_CLOCK) -> None:
    """A reviewer takes an item from the pool (or a lead takes anyone's) and starts reviewing it:
    submitted or needs_rereview -> in_review. Claiming an item already yours just starts the review."""
    require_role(actor, *REVIEW_ROLES)
    now = clock.now()
    with transaction.atomic():
        item = locked_item(item_id)
        status = ItemStatus(item.status)
        if status not in CLAIMABLE:
            raise InvalidTransition(action="claim", from_status=status)
        if item.owner_id == actor.pk:  # pyrefly: ignore[missing-attribute]
            raise NotPermitted("You can't review your own submission.")
        holder = item.assignee
        if holder is not None and holder.pk != actor.pk and not has_role(actor, Role.LEAD):
            raise NotPermitted(f"{_name(holder)} has this item. Ask a lead to reassign it.")
        if holder is None or holder.pk != actor.pk:
            _acquire_lock()
            reason = "Claimed from the pool" if holder is None else f"Claimed from {_name(holder)}"
            _set_assignee(item, actor, actor=actor, mode=AssignmentMode.CLAIM, reason=reason, at=now)
        if status in (ItemStatus.SUBMITTED, ItemStatus.NEEDS_REREVIEW):
            start_review(item, reviewer=actor, at=now)


def _target(assignee_id: int | None, item: ReviewItem) -> User | None:
    if assignee_id is None:
        return None
    user = User.objects.filter(pk=assignee_id).first()
    if user is None or not has_role(user, *REVIEW_ROLES):
        raise InvalidInput.for_field("assignee_id", "Pick an active reviewer.")
    if user.pk == item.owner_id:  # pyrefly: ignore[missing-attribute]
        raise InvalidInput.for_field("assignee_id", "The submitter can't review their own item.")
    return user


def assign_item(
    *, actor: User, item_id: int, assignee_id: int | None, reason: str = "", clock: Clock = SYSTEM_CLOCK
) -> None:
    """Leads and admins assign anything (mode manual); a reviewer hands off an item assigned to them (mode
    handoff). `assignee_id=None` returns the item to the pool. Assigning to the current assignee is a no-op."""
    now = clock.now()
    with transaction.atomic():
        item = locked_item(item_id)
        status = ItemStatus(item.status)
        if has_role(actor, Role.LEAD, Role.ADMIN):
            mode = AssignmentMode.MANUAL
        elif has_role(actor, *REVIEW_ROLES) and item.assignee_id == actor.pk:  # pyrefly: ignore[missing-attribute]
            mode = AssignmentMode.HANDOFF
        else:
            raise NotPermitted("Only a lead can reassign this item; reviewers can hand off their own.")
        if status not in ASSIGNABLE:
            raise InvalidTransition(action="assign", from_status=status)
        target = _target(assignee_id, item)
        if (target.pk if target else None) == item.assignee_id:  # pyrefly: ignore[missing-attribute]
            return
        default = "Returned to the pool" if target is None else f"Assigned by {_name(actor)}"
        if mode is AssignmentMode.HANDOFF and target is not None:
            default = f"Handed off by {_name(actor)}"
        _acquire_lock()
        _set_assignee(item, target, actor=actor, mode=mode, reason=reason.strip() or default, at=now)


@dataclass(frozen=True)
class BulkSkip:
    item_id: int
    code: str
    message: str


@dataclass(frozen=True)
class BulkResult:
    succeeded: tuple[int, ...]
    skipped: tuple[BulkSkip, ...]


def run_bulk(item_ids: Iterable[int], action: Callable[[int], object]) -> BulkResult:
    """Apply `action` to each item in its own transaction. A domain error skips that item with its code; every
    other exception propagates. Bulk actions (assign; F's fast-track approve) report skips as values."""
    succeeded: list[int] = []
    skipped: list[BulkSkip] = []
    for item_id in dict.fromkeys(item_ids):
        try:
            action(item_id)
        except DomainError as exc:  # the one place a bulk action can decide: skip the item, keep going
            skipped.append(BulkSkip(item_id=item_id, code=exc.code, message=exc.message))
        else:
            succeeded.append(item_id)
    return BulkResult(succeeded=tuple(succeeded), skipped=tuple(skipped))


def bulk_assign(
    *, actor: User, item_ids: Iterable[int], assignee_id: int | None, reason: str = "", clock: Clock = SYSTEM_CLOCK
) -> BulkResult:
    """Lead/admin only. Each item is assigned in its own transaction; problems are reported per item."""
    require_role(actor, Role.LEAD, Role.ADMIN)
    return run_bulk(
        item_ids,
        lambda item_id: assign_item(actor=actor, item_id=item_id, assignee_id=assignee_id, reason=reason, clock=clock),
    )
