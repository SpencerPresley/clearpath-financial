"""Decisions and their gates (spec §4.2 ruling 3), reaffirm, and pull.

Gates on the version being approved, in this order, each its own 409:
1. the copy quotes no superseded offer terms (`stale_offer_terms`): first, because triage can't fix it;
2. no open finding (`open_findings_block_decision`), warnings and human checklist items included;
3. no accepted finding (`accepted_findings_block_approval`): accepted means "must change", and the approved
   version is exactly what goes live (approve with edits checks the reviewer's v+1, where vN's accepted
   findings were addressed);
4. the AI check isn't pending or running (`ai_check_pending`); if it failed, `llm_override_reason` is required.
Request changes and Reject need only a reason. Every decision records the exact version, the offer-terms
versions it quotes, the rule-set date and engine version, evidence hashes, the approver, and (approvals) expiry.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from audit.payloads import DecisionRecordedPayload, ItemWithdrawnPayload, TakedownRequestedPayload
from audit.services import record_event
from checks.engine import ENGINE_VERSION, RULESET_VERSION
from checks.models import Finding, TermsRef
from checks.services import recount_open_findings, run_code_checks
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    Channel,
    CheckStatus,
    DecisionLane,
    DecisionOutcome,
    EntityType,
    EventType,
    ExpiryRule,
    FindingState,
    ItemStatus,
    TakedownState,
    VersionOrigin,
)
from core.errors import AiCheckPending, Conflict, InvalidInput, OpenFindingsBlockDecision
from reviews.assignment import locked_item, require_reviewer_of
from reviews.errors import (
    AcceptedFindingsBlockApproval,
    DriftNotRestored,
    FindingsNeedTriage,
    FindingSummary,
    StaleOfferTerms,
    StaleVersion,
)
from reviews.models import (
    APPROVED_OUTCOMES,
    Attachment,
    Decision,
    DecisionEvidence,
    DecisionTermsVersion,
    ExpiryPolicy,
    Placement,
    ReviewItem,
    Version,
)
from reviews.months import add_months
from reviews.selectors import drift_rereview, live_placements_q
from reviews.transitions import Action, apply_transition, require_transition, start_review
from reviews.versions import create_version

# An approval whose channel has no ExpiryPolicy row (an admin deleted it) lasts this long: the shortest default.
DEFAULT_EXPIRY_MONTHS: Final = 6


# --- expiry ----------------------------------------------------------------------------------------------------


def approval_expiry(
    *,
    channel: Channel,
    decided_at: datetime,
    planned_first_run: date | None,
    planned_last_run: date | None,
    today: date,
) -> datetime:
    """When an approval lapses (decisions.md "Approval expiry", ExpiryPolicy per channel).

    `fixed_months`: decided_at + N months. `send_window` (one-off sends): midnight after the planned send window
    ends, or after today if the window is already over, so an approval never expires before the sweep sees it.
    """
    policy = ExpiryPolicy.objects.filter(channel=channel).first()
    if policy is None:
        return add_months(decided_at, DEFAULT_EXPIRY_MONTHS)
    if ExpiryRule(policy.rule) is ExpiryRule.FIXED_MONTHS and policy.months is not None:
        return add_months(decided_at, policy.months)
    window_end = max(planned_last_run or planned_first_run or today, today)
    return datetime.combine(window_end + timedelta(days=1), time.min, tzinfo=timezone.get_default_timezone())


# --- gates -----------------------------------------------------------------------------------------------------


def _current(item: ReviewItem, version_n: int) -> Version:
    current = item.current_version
    if current is None or current.n != version_n:
        raise StaleVersion(version_n=version_n, current_n=current.n if current is not None else None)
    return current


def _states(version: Version) -> dict[FindingState, int]:
    counts: dict[FindingState, int] = {}
    for state in Finding.objects.filter(version=version).values_list("state", flat=True):
        counts[FindingState(state)] = counts.get(FindingState(state), 0) + 1
    return counts


def _require_triaged(version: Version) -> None:
    open_count = _states(version).get(FindingState.OPEN, 0)
    if open_count:
        raise OpenFindingsBlockDecision(open_count=open_count)


def _require_ai_done(item: ReviewItem, override: str | None) -> str:
    """The AI gate. Returns the override reason to record ("" if none was needed)."""
    status = CheckStatus(item.llm_check_status)
    if status in (CheckStatus.PENDING, CheckStatus.RUNNING):
        raise AiCheckPending
    if status is CheckStatus.FAILED:
        if not (override or "").strip():
            raise InvalidInput.for_field(
                "llm_override_reason", "The AI check failed. Say why you're approving without it."
            )
        return (override or "").strip()
    return ""


def _require_current_terms(version: Version, at: datetime) -> tuple[int, ...]:
    """The offer-terms versions the copy quotes; refuses any not in effect at `at` (ruling in the plan: F's
    fan-out finds approvals by the terms version they quote, so an approval must never record a dead one)."""
    refs = TermsRef.objects.filter(version=version).select_related("offer_terms").order_by("offer_terms_id")
    terms = {ref.offer_terms.pk: ref.offer_terms for ref in refs}
    stale = [
        t
        for t in terms.values()
        if not (t.effective_range.lower <= at and (t.effective_range.upper is None or at < t.effective_range.upper))
    ]  # pyrefly: ignore[missing-attribute]
    if stale:
        raise StaleOfferTerms(versions=[f"{t.product} v{t.version}" for t in stale])
    return tuple(terms)


def _require_approvable(
    item: ReviewItem, version: Version, *, override: str | None, at: datetime
) -> tuple[str, tuple[int, ...]]:
    """Every approval gate on the version being approved, in the module docstring's order. Returns (override
    reason to record, quoted terms ids)."""
    terms_ids = _require_current_terms(version, at)
    _require_triaged(version)
    accepted = _states(version).get(FindingState.ACCEPTED, 0)
    if accepted:
        raise AcceptedFindingsBlockApproval(accepted_count=accepted)
    return _require_ai_done(item, override), terms_ids


def _open_summaries(version: Version) -> list[FindingSummary]:
    return [
        FindingSummary(
            id=f.pk, rule_id=f.rule_id, severity=f.severity, source=f.source, message=f.message, quote=f.quote
        )
        for f in Finding.objects.filter(version=version, state=FindingState.OPEN.value).order_by(
            "severity", "span_start", "pk"
        )
    ]


def _evidence(item: ReviewItem, attachment_ids: Sequence[int]) -> list[Attachment]:
    """Evidence must be attached to this item, one of its versions, or its partner (the agreement)."""
    ids = list(dict.fromkeys(attachment_ids))
    if not ids:
        return []
    owned = Q(item_id=item.pk) | Q(version__item_id=item.pk)
    if item.partner_id is not None:  # pyrefly: ignore[missing-attribute]
        owned |= Q(partner_id=item.partner_id)  # pyrefly: ignore[missing-attribute]
    found = {a.pk: a for a in Attachment.objects.filter(owned, pk__in=ids)}
    if len(found) != len(ids):
        raise InvalidInput.for_field("evidence_attachment_ids", "Some evidence isn't attached to this item.")
    return [found[i] for i in ids]


# --- writing the decision --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionInput:
    outcome: DecisionOutcome
    version_n: int
    reason: str
    evidence_attachment_ids: tuple[int, ...] = ()
    llm_override_reason: str | None = None
    edited_content_text: str | None = None  # approve with edits: the reviewer's v+1
    lane: DecisionLane = DecisionLane.STANDARD


@dataclass(frozen=True)
class DecisionResult:
    decision_id: int
    version_n: int
    status: ItemStatus


@dataclass(frozen=True)
class _Approval:
    expires_at: datetime
    override: str
    terms_ids: tuple[int, ...]


def _write(  # noqa: PLR0913  # the decision's columns
    item: ReviewItem,
    version: Version,
    *,
    action: Action,
    outcome: DecisionOutcome,
    lane: DecisionLane,
    actor: User,
    reason: str,
    evidence: Sequence[Attachment],
    approval: _Approval | None,
    clock: Clock,
) -> Decision:
    at = clock.now()
    carried_from = version.based_on if VersionOrigin(version.origin) is not VersionOrigin.SUBMISSION else None
    decision = Decision.objects.create(
        item=item,
        version=version,
        outcome=outcome,
        lane=lane,
        approver=actor,
        reason=reason,
        ruleset_date=RULESET_VERSION,
        engine_version=ENGINE_VERSION,
        expires_at=approval.expires_at if approval else None,
        llm_override_reason=approval.override if approval else "",
        ai_review_carried_from=carried_from,
        decided_at=at,
    )
    terms_ids = approval.terms_ids if approval else ()
    DecisionTermsVersion.objects.bulk_create(
        [DecisionTermsVersion(decision=decision, offer_terms_id=t) for t in terms_ids]
    )
    DecisionEvidence.objects.bulk_create(
        [DecisionEvidence(decision=decision, attachment=a, sha256=a.sha256) for a in evidence]
    )
    apply_transition(
        item,
        action,
        actor=actor,
        at=at,
        entity=EntityType.DECISION,
        entity_id=decision.pk,
        payload=DecisionRecordedPayload(
            decision_id=decision.pk,
            version_id=version.pk,
            outcome=outcome,
            lane=lane,
            reason=reason,
            expires_at=decision.expires_at,
            terms_version_ids=terms_ids,
            evidence_attachment_ids=tuple(a.pk for a in evidence),
            ruleset_date=RULESET_VERSION,
            engine_version=ENGINE_VERSION,
            ai_review_carried_from_version_id=carried_from.pk if carried_from else None,
            llm_override_reason=decision.llm_override_reason,
        ),
    )
    if approval is not None:
        item.approved_at = at
        item.approval_expires_at = approval.expires_at
        item.save(update_fields=["approved_at", "approval_expires_at"])
    if action is Action.REJECT:
        # Rejecting content that's still running (a re-review taken to full review) must take it down too.
        live = Placement.objects.select_for_update().filter(live_placements_q(clock.today()), item=item)
        _request_takedowns(item, list(live), reason=reason, actor=actor, at=at)
    return decision


def _approval(item: ReviewItem, version: Version, *, override: str | None, clock: Clock) -> _Approval:
    now = clock.now()
    recorded_override, terms_ids = _require_approvable(item, version, override=override, at=now)
    expires_at = approval_expiry(
        channel=Channel(item.channel),
        decided_at=now,
        planned_first_run=item.planned_first_run,
        planned_last_run=item.planned_last_run,
        today=clock.today(),
    )
    return _Approval(expires_at=expires_at, override=recorded_override, terms_ids=terms_ids)


_ACTIONS: Final = {
    (DecisionLane.STANDARD, DecisionOutcome.APPROVED): Action.APPROVE,
    (DecisionLane.STANDARD, DecisionOutcome.APPROVED_WITH_EDITS): Action.APPROVE,
    (DecisionLane.STANDARD, DecisionOutcome.CHANGES_REQUESTED): Action.REQUEST_CHANGES,
    (DecisionLane.STANDARD, DecisionOutcome.REJECTED): Action.REJECT,
    (DecisionLane.FAST_TRACK, DecisionOutcome.APPROVED): Action.FAST_TRACK_APPROVE,
}


def _edited_version(
    item: ReviewItem, reviewed: Version, *, actor: User, data: DecisionInput, clock: Clock
) -> tuple[Version, FindingsNeedTriage | None]:
    """The version an approve-with-edits approves: the reviewer's new v+1, or (re-posting after triage) the
    current reviewer-edit version. Returns it with the refusal to raise if v+1 has open findings."""
    if data.edited_content_text is None:
        if VersionOrigin(reviewed.origin) is not VersionOrigin.REVIEWER_EDIT or reviewed.decisions.exists():
            # Only the reviewer-edit version still waiting from a refused edit can be approved without text.
            raise InvalidInput.for_field("edited_content_text", "Include your edited copy.")
        return reviewed, None
    _require_triaged(reviewed)
    _require_ai_done(item, data.llm_override_reason)
    edited = create_version(
        item=item,
        text=data.edited_content_text,
        author=actor,
        origin=VersionOrigin.REVIEWER_EDIT,
        based_on=reviewed,
        clock=clock,
    ).version
    pending = _open_summaries(edited)
    return edited, FindingsNeedTriage(version_n=edited.n, findings=pending) if pending else None


def record_decision(*, actor: User, item_id: int, data: DecisionInput, clock: Clock = SYSTEM_CLOCK) -> DecisionResult:
    """Approve, approve with edits, request changes, or reject the current version (`data.version_n`; anything
    else is `stale_version`). On a `submitted` item the decision first starts the review.

    Approve with edits, with `edited_content_text`: the reviewed version must be fully triaged and its AI check
    done; the reviewer's text becomes v+1 (`reviewer_edit`, code checks run, identical dismissals carried). If
    v+1 has open findings, v+1 is kept as the current version and `findings_need_triage` (409) returns them; the
    reviewer triages and posts `approved_with_edits` again on v+1 without text. Otherwise v+1 is approved now.

    `lane=fast_track` (workstream F): approve a needs_rereview item's generated fast-track version.
    """
    action = _ACTIONS.get((data.lane, data.outcome))
    if action is None:
        raise InvalidInput.for_field("outcome", f"A {data.lane} decision can't be {data.outcome}.")
    reason = data.reason.strip()
    if not reason:
        raise InvalidInput.for_field("reason", "Give a reason for the decision.")
    now = clock.now()
    refusal: FindingsNeedTriage | None = None
    with transaction.atomic():
        item = locked_item(item_id)
        require_reviewer_of(actor, item)
        version = _current(item, data.version_n)
        if data.lane is DecisionLane.STANDARD and ItemStatus(item.status) is ItemStatus.SUBMITTED:
            start_review(item, reviewer=actor, at=now)
        require_transition(item, action)
        evidence = _evidence(item, data.evidence_attachment_ids)
        if data.lane is DecisionLane.FAST_TRACK and VersionOrigin(version.origin) is not VersionOrigin.FAST_TRACK:
            raise Conflict(
                "Only a generated terms-change version can be fast-tracked.", details={"version_n": version.n}
            )
        approval: _Approval | None = None
        if data.outcome is DecisionOutcome.APPROVED_WITH_EDITS:
            version, refusal = _edited_version(item, version, actor=actor, data=data, clock=clock)
            if refusal is None:
                approval = _approval(item, version, override=data.llm_override_reason, clock=clock)
        elif data.outcome is DecisionOutcome.APPROVED:
            approval = _approval(item, version, override=data.llm_override_reason, clock=clock)
        result: DecisionResult | FindingsNeedTriage
        if refusal is not None:
            result = refusal
        else:
            written = _write(
                item,
                version,
                action=action,
                outcome=data.outcome,
                lane=data.lane,
                actor=actor,
                reason=reason,
                evidence=evidence,
                approval=approval,
                clock=clock,
            )
            result = _result(written, item)
    if isinstance(result, FindingsNeedTriage):
        raise result  # after the commit: v+1 and its findings are kept for triage
    return result


def _result(decision: Decision, item: ReviewItem) -> DecisionResult:
    return DecisionResult(decision_id=decision.pk, version_n=decision.version.n, status=ItemStatus(item.status))


def _approved_version_n(item: ReviewItem) -> int | None:
    decision = Decision.objects.filter(item=item, outcome__in=APPROVED_OUTCOMES).order_by("-decided_at", "-pk").first()
    return decision.version.n if decision is not None else None


def reaffirm(
    *, actor: User, item_id: int, reason: str, llm_override_reason: str | None = None, clock: Clock = SYSTEM_CLOCK
) -> DecisionResult:
    """needs_rereview -> approved on the same (approved, current) version, with a fresh expiry.

    The code checks re-run first against today's rules and terms: catching rule changes is what expiry is for.
    New findings are kept and the reaffirm refused (`findings_need_triage`) until they're triaged; the usual
    approval gates then apply, so copy quoting superseded terms can't be reaffirmed (fast-track or pull it). If
    the version's AI check failed, `llm_override_reason` is required again: a reaffirm is a new approval. A
    drift_detected re-review is refused (`drift_not_restored`) until the placement's latest check finds the
    approved copy again: otherwise Check now or Pull.
    """
    reason = reason.strip()
    if not reason:
        raise InvalidInput.for_field("reason", "Give a reason for the decision.")
    result: DecisionResult | FindingsNeedTriage
    with transaction.atomic():
        item = locked_item(item_id)
        require_reviewer_of(actor, item)
        require_transition(item, Action.REAFFIRM)
        drift = drift_rereview(item_id=item.pk)
        if drift is not None and not drift.restored:
            raise DriftNotRestored(placement_id=drift.placement_id)
        version = item.current_version
        if version is None or _approved_version_n(item) != version.n:
            raise Conflict(
                "The current version isn't the approved one. Fast-track it or review it.",
                details={"version_n": version.n if version else None},
            )
        before = {f.pk for f in Finding.objects.filter(version=version)}
        run_code_checks(version=version, clock=clock)
        recount_open_findings(item_id=item.pk)
        new = [f for f in _open_summaries(version) if f.id not in before]
        if new:
            result = FindingsNeedTriage(version_n=version.n, findings=new)
        else:
            approval = _approval(item, version, override=llm_override_reason, clock=clock)
            written = _write(
                item,
                version,
                action=Action.REAFFIRM,
                outcome=DecisionOutcome.APPROVED,
                lane=DecisionLane.REAFFIRM,
                actor=actor,
                reason=reason,
                evidence=[],
                approval=approval,
                clock=clock,
            )
            result = _result(written, item)
    if isinstance(result, FindingsNeedTriage):
        raise result  # after the commit: the re-check's findings are kept for triage
    return result


def _request_takedowns(
    item: ReviewItem, placements: Sequence[Placement], *, reason: str, actor: User, at: datetime
) -> list[int]:
    """Mark each placement's takedown requested (TAKEDOWN_REQUESTED each); returns their ids. Placements already
    requested are included but not re-recorded."""
    requested: list[int] = []
    for placement in placements:
        requested.append(placement.pk)
        if placement.takedown_state is not None:
            continue
        placement.takedown_state = TakedownState.REQUESTED
        placement.takedown_requested_at = at
        placement.save(update_fields=["takedown_state", "takedown_requested_at"])
        record_event(
            type=EventType.TAKEDOWN_REQUESTED,
            entity=EntityType.PLACEMENT,
            entity_id=placement.pk,
            item_id=item.pk,
            payload=TakedownRequestedPayload(placement_id=placement.pk, reason=reason),
            actor=actor,
            at=at,
        )
    return requested


def pull_item(
    *, actor: User, item_id: int, reason: str, placement_ids: Sequence[int] = (), clock: Clock = SYSTEM_CLOCK
) -> None:
    """needs_rereview -> withdrawn, requesting takedown of the given placements (default: every live one).
    "Time to fix live content" stops when the takedown is confirmed (ruling 6)."""
    reason = reason.strip()
    if not reason:
        raise InvalidInput.for_field("reason", "Say why the content is pulled.")
    now = clock.now()
    with transaction.atomic():
        item = locked_item(item_id)
        require_reviewer_of(actor, item)
        require_transition(item, Action.PULL)
        if placement_ids:
            ids = list(dict.fromkeys(placement_ids))
            placements = list(
                Placement.objects.select_for_update().filter(live_placements_q(clock.today()), item=item, pk__in=ids)
            )
            if len(placements) != len(ids):
                raise InvalidInput.for_field("placement_ids", "Pick live placements of this item.")
        else:
            placements = list(Placement.objects.select_for_update().filter(live_placements_q(clock.today()), item=item))
        requested = _request_takedowns(item, placements, reason=reason, actor=actor, at=now)
        apply_transition(
            item,
            Action.PULL,
            actor=actor,
            at=now,
            payload=ItemWithdrawnPayload(reason=reason, placement_ids=tuple(sorted(requested))),
        )
