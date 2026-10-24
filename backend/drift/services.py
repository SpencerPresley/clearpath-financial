"""Drift checks of monitored placements (product-spec "Drift monitoring"). The only writers of `reviews.Snapshot`.

A check is a Snapshot moving pending -> running -> succeeded | failed:

- `request_check` (a person's "Check now", or the daily sweep) writes a pending snapshot and
  DRIFT_CHECK_REQUESTED, and enqueues `drift.run_check` once that commits. One check per placement is in flight at
  a time (a partial unique index); asking again returns the one in flight.
- The task `claim`s it, fetches the page outside any transaction (`drift.fetcher`), then calls `complete` or
  `fail`. Scheduled checks retry transient failures (`should_retry` / `release`); manual ones get one attempt, and
  the person can press the button again.
- `complete` compares the page with the item's **latest approved version** (not `Placement.approved_version`, which
  is fixed when the placement is recorded: after a terms fast-track the partner should show v+1), runs the code
  rules on the whole page, and records DRIFT_CHECKED. If the copy is modified or missing, the item is approved and
  not legacy, and the placement is live, the item goes to needs_rereview(drift_detected) with the snapshot linked.
  Any other status records the check only (an item already in re-review isn't sent back twice).
- If the copy is unchanged but the page has blocking findings that don't fire on the approved copy (partner text
  added beside intact copy), nothing transitions: PAGE_FINDINGS_FLAGGED is recorded (the assignee and the active
  leads are notified) when that set of rules wasn't already on the previous successful check, so a daily sweep
  doesn't repeat the same alert. The review screen shows the placement's attention state from the snapshot.
- A fetch failure is never a result: it ends `failed` with an error code, which the review screen shows. But a page
  that is gone (HTTP 404/410) on GONE_AFTER consecutive checks of a live placement counts as missing copy: the item
  is reopened (drift_detected) with those failed checks linked. A success, or any other failure, ends the streak.
- `reconcile` (beat) fails checks stuck running and re-enqueues pending ones whose message was lost.
"""

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final

from django.db import transaction
from django.db.models import Q

from accounts.models import User
from audit.payloads import DriftCheckedPayload, DriftCheckRequestedPayload, PageFindingsFlaggedPayload
from audit.services import record_event
from checks.engine import run_code_checks as run_engine
from checks.services import rule_context
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import (
    CheckStatus,
    DriftResult,
    DriftTrigger,
    EntityType,
    EventType,
    ItemStatus,
    ReopenReason,
    Role,
    Severity,
)
from core.errors import Conflict, NotFound, NotPermitted
from core.permissions import has_role
from drift.compare import Comparison, compare
from drift.extract import MAX_TEXT_CHARS, PageText, visible_text
from drift.fetcher import FetchedPage, FetchError
from reviews.assignment import locked_item
from reviews.models import APPROVED_OUTCOMES, Decision, Placement, ReviewItem, Snapshot, Version
from reviews.rereview import reopen_item
from reviews.selectors import live_placements_q

logger = logging.getLogger(__name__)

IN_FLIGHT: Final = (CheckStatus.PENDING.value, CheckStatus.RUNNING.value)
MAX_SCHEDULED_ATTEMPTS: Final = 3
STUCK_AFTER: Final = timedelta(minutes=10)
LOST_AFTER: Final = timedelta(hours=1)  # pending this long: stop re-enqueueing, fail it
_DRIFTED: Final = frozenset({DriftResult.MODIFIED, DriftResult.MISSING})
GONE_HTTP_STATUSES: Final = frozenset({404, 410})
GONE_AFTER: Final = 3  # consecutive gone checks of a live placement that count as missing copy


def _enqueue(snapshot_id: int) -> None:
    from drift.tasks import run_check  # noqa: PLC0415  # tasks import this module

    run_check.delay(snapshot_id)


enqueue: Callable[[int], None] = _enqueue  # seam: tests record instead of calling Celery


@dataclass(frozen=True)
class Claim:
    snapshot_id: int
    placement_id: int
    item_id: int
    url: str
    attempt: int
    trigger: DriftTrigger


@dataclass(frozen=True)
class CheckOutcome:
    snapshot_id: int
    result: DriftResult | None  # None: nothing recorded (the claim was stale)
    reopened: bool
    flagged: bool = False  # PAGE_FINDINGS_FLAGGED recorded


@dataclass(frozen=True)
class SweepResult:
    requested: tuple[int, ...]  # placement ids
    skipped: tuple[int, ...]


@dataclass(frozen=True)
class ReconcileResult:
    failed: tuple[int, ...]  # snapshot ids
    requeued: tuple[int, ...]


@dataclass(frozen=True)
class CheckRow:
    """A finished check, as the gone streak reads it."""

    id: int
    status: CheckStatus
    http_status: int | None
    reopened: bool  # this check sent the item to re-review


def gone_streak(rows: Iterable[CheckRow]) -> tuple[int, ...]:
    """The ids of the consecutive gone (failed with HTTP 404/410) checks at the head of `rows` (newest first). A
    success or any other failure ends it, and so does a check that already reopened the item: that streak is spent,
    so a page that stays gone doesn't send the item back again on the very next check."""
    streak: list[int] = []
    for row in rows:
        if row.status is not CheckStatus.FAILED or row.http_status not in GONE_HTTP_STATUSES or row.reopened:
            break
        streak.append(row.id)
    return tuple(streak)


def new_blocking_rules(findings: Iterable[dict[str, object]]) -> frozenset[str]:
    """Rules with a blocking finding on the page that don't fire on the approved copy itself."""
    return frozenset(
        str(f["rule_id"]) for f in findings if f.get("new") is True and f.get("severity") == Severity.BLOCKING.value
    )


# --- requesting ------------------------------------------------------------------------------------------------


def _require_checker(actor: User, item: ReviewItem) -> None:
    if item.owner_id != actor.pk and not has_role(actor, Role.REVIEWER, Role.LEAD, Role.ADMIN):  # pyrefly: ignore[missing-attribute]
        raise NotPermitted("Only the submitter or a reviewer can check a placement.")


def request_check(*, actor: User | None, placement_id: int, trigger: DriftTrigger, clock: Clock = SYSTEM_CLOCK) -> int:
    """Queue a check of the placement's page; returns the snapshot id (the in-flight one if there is one)."""
    now = clock.now()
    with transaction.atomic():
        item_id = Placement.objects.filter(pk=placement_id).values_list("item_id", flat=True).first()
        if item_id is None:
            raise NotFound.entity("placement", placement_id)
        item = locked_item(item_id)  # item first (lock order), then the placement
        placement = Placement.objects.select_for_update().get(pk=placement_id)
        if actor is not None:
            _require_checker(actor, item)
        if not placement.url:
            raise Conflict("This placement has no web address to check.", details={"placement_id": placement_id})
        in_flight = Snapshot.objects.filter(placement=placement, status__in=IN_FLIGHT).values_list("pk", flat=True)
        if (existing := in_flight.first()) is not None:
            return existing
        snapshot = Snapshot.objects.create(
            placement=placement,
            status=CheckStatus.PENDING.value,
            trigger=trigger.value,
            requested_by=actor,
            requested_at=now,
            url=placement.url,
        )
        record_event(
            type=EventType.DRIFT_CHECK_REQUESTED,
            entity=EntityType.PLACEMENT,
            entity_id=placement.pk,
            item_id=item.pk,
            payload=DriftCheckRequestedPayload(placement_id=placement.pk, snapshot_id=snapshot.pk, trigger=trigger),
            actor=actor,
            at=now,
        )
        snapshot_id = snapshot.pk
        transaction.on_commit(lambda: enqueue(snapshot_id))
    return snapshot_id


# --- running ---------------------------------------------------------------------------------------------------


def claim(*, snapshot_id: int, clock: Clock = SYSTEM_CLOCK) -> Claim | None:
    """pending -> running. None if the snapshot isn't pending (a duplicate delivery or a reconciled check)."""
    with transaction.atomic():
        snapshot = (
            Snapshot.objects.select_for_update()
            .select_related("placement")
            .filter(pk=snapshot_id, status=CheckStatus.PENDING.value)
            .first()
        )
        if snapshot is None:
            return None
        snapshot.status = CheckStatus.RUNNING.value
        snapshot.started_at = clock.now()
        snapshot.attempts += 1
        snapshot.save(update_fields=["status", "started_at", "attempts"])
    return Claim(
        snapshot_id=snapshot.pk,
        placement_id=snapshot.placement_id,  # pyrefly: ignore[missing-attribute]
        item_id=snapshot.placement.item_id,  # pyrefly: ignore[missing-attribute]
        url=snapshot.url,
        attempt=snapshot.attempts,
        trigger=DriftTrigger(snapshot.trigger),
    )


def should_retry(*, claim: Claim, error: FetchError) -> bool:
    return claim.trigger is DriftTrigger.SCHEDULED and error.transient and claim.attempt < MAX_SCHEDULED_ATTEMPTS


def release(*, claim: Claim, clock: Clock = SYSTEM_CLOCK) -> None:  # noqa: ARG001  # same shape as the others
    """running -> pending, for a retry. The attempt count stays."""
    Snapshot.objects.filter(pk=claim.snapshot_id, status=CheckStatus.RUNNING.value, attempts=claim.attempt).update(
        status=CheckStatus.PENDING.value, started_at=None
    )


def _locked_running(claim: Claim) -> Snapshot | None:
    """The claim's snapshot, locked, if it is still this claim's run."""
    return (
        Snapshot.objects.select_for_update()
        .filter(pk=claim.snapshot_id, status=CheckStatus.RUNNING.value, attempts=claim.attempt)
        .first()
    )


def _latest_approved_version(item_id: int) -> Version | None:
    approval = (
        Decision.objects.filter(item_id=item_id, outcome__in=APPROVED_OUTCOMES)
        .select_related("version")
        .order_by("-decided_at", "-pk")
        .first()
    )
    return approval.version if approval is not None else None


@dataclass(frozen=True)
class _Analysis:
    version_id: int
    comparison: Comparison
    findings: list[dict[str, object]]


def _analyse(version: Version, text: str, clock: Clock) -> _Analysis:
    """Compare the page with `version`, and run the code rules on the whole page with the version's context (its
    product, channel, markets, partner, evidence, and the terms in effect now). A finding is `new` when its rule
    doesn't fire on the approved copy itself."""
    ctx = rule_context(version=version, clock=clock)
    on_copy = {f.rule_id for f in run_engine(ctx).findings}
    page_findings = run_engine(replace(ctx, text=text)).findings
    findings: list[dict[str, object]] = [
        {
            "rule_id": f.rule_id,
            "citation": f.citation,
            "severity": str(f.severity),
            "message": f.message,
            "suggested_fix": f.suggested_fix,
            "quote": f.quote,
            "new": f.rule_id not in on_copy,
        }
        for f in sorted(page_findings, key=lambda f: (f.rule_id in on_copy, f.span.start if f.span else -1))
    ]
    return _Analysis(version_id=version.pk, comparison=compare(version.content_text, text), findings=findings)


def _page_text(page: FetchedPage) -> PageText:
    if page.content_type == "text/html":
        return visible_text(page.text)
    return PageText(title=None, text=page.text[:MAX_TEXT_CHARS])


def complete(*, claim: Claim, page: FetchedPage, clock: Clock = SYSTEM_CLOCK) -> CheckOutcome:
    """Record a fetched page's result; reopen the item if its live copy drifted (see the module docstring)."""
    extracted = _page_text(page)
    version = _latest_approved_version(claim.item_id)
    analysis = _analyse(version, extracted.text, clock) if version is not None else None  # CPU outside the lock
    now = clock.now()
    with transaction.atomic():
        item = locked_item(claim.item_id)
        snapshot = _locked_running(claim)
        if snapshot is None:
            logger.info("drift check stale snapshot_id=%d attempt=%d", claim.snapshot_id, claim.attempt)
            return CheckOutcome(snapshot_id=claim.snapshot_id, result=None, reopened=False)
        current = _latest_approved_version(item.pk)
        if current is None:
            _record_failure(
                snapshot, item, code="no_approved_version", message="The item has no approved version.", at=now
            )
            return CheckOutcome(snapshot_id=snapshot.pk, result=None, reopened=False)
        if analysis is None or analysis.version_id != current.pk:  # approved again while we fetched
            analysis = _analyse(current, extracted.text, clock)
        comparison = analysis.comparison
        snapshot.status = CheckStatus.SUCCEEDED.value
        snapshot.finished_at = now
        snapshot.final_url = page.final_url[:2000]
        snapshot.http_status = page.status
        snapshot.title = (extracted.title or "")[:500]
        snapshot.text = extracted.text
        snapshot.content_sha256 = hashlib.sha256(extracted.text.encode()).hexdigest()
        snapshot.compared_version = current
        snapshot.result = comparison.result.value
        snapshot.score = comparison.score
        snapshot.matched_text = comparison.matched_text
        snapshot.diff = [{"op": s.op.value, "text": s.text} for s in comparison.diff]
        snapshot.findings = analysis.findings
        snapshot.save()
        record_event(
            type=EventType.DRIFT_CHECKED,
            entity=EntityType.PLACEMENT,
            entity_id=claim.placement_id,
            item_id=item.pk,
            payload=DriftCheckedPayload(
                placement_id=claim.placement_id,
                snapshot_id=snapshot.pk,
                status=CheckStatus.SUCCEEDED,
                result=comparison.result,
                compared_version_id=current.pk,
                score=comparison.score,
                findings_count=len(analysis.findings),
                new_findings_count=sum(1 for f in analysis.findings if f["new"]),
            ),
            actor=None,
            at=now,
        )
        reopened = comparison.result in _DRIFTED and _at_risk(item, claim.placement_id, clock)
        if reopened:
            event_id = reopen_item(
                item_id=item.pk, reason=ReopenReason.DRIFT_DETECTED, clock=clock, snapshot_id=snapshot.pk
            )
            snapshot.reopen_event_id = event_id  # pyrefly: ignore[missing-attribute]
            snapshot.save(update_fields=["reopen_event"])
        flagged = comparison.result is DriftResult.UNCHANGED and _flag_page_findings(item, snapshot, clock=clock)
    return CheckOutcome(snapshot_id=claim.snapshot_id, result=comparison.result, reopened=reopened, flagged=flagged)


def _flag_page_findings(item: ReviewItem, snapshot: Snapshot, *, clock: Clock) -> bool:
    """Record PAGE_FINDINGS_FLAGGED if the page has new blocking rules the previous successful check didn't have,
    and the item is approved and the placement live (otherwise a reviewer already has it, or nothing is at risk)."""
    rules = new_blocking_rules(snapshot.findings)
    if not rules:
        return False
    previous = (
        Snapshot.objects.filter(placement_id=snapshot.placement_id, status=CheckStatus.SUCCEEDED.value)  # pyrefly: ignore[missing-attribute]
        .exclude(pk=snapshot.pk)
        .order_by("-requested_at", "-pk")
        .values_list("findings", flat=True)
        .first()
    )
    if rules <= new_blocking_rules(previous or []):
        return False
    if not _at_risk(item, snapshot.placement_id, clock):  # pyrefly: ignore[missing-attribute]
        return False
    record_event(
        type=EventType.PAGE_FINDINGS_FLAGGED,
        entity=EntityType.PLACEMENT,
        entity_id=snapshot.placement_id,  # pyrefly: ignore[missing-attribute]
        item_id=item.pk,
        payload=PageFindingsFlaggedPayload(
            placement_id=snapshot.placement_id,  # pyrefly: ignore[missing-attribute]
            snapshot_id=snapshot.pk,
            rule_ids=sorted(rules),
        ),
        actor=None,
        at=clock.now(),
    )
    return True


def _at_risk(item: ReviewItem, placement_id: int, clock: Clock) -> bool:
    if item.status != ItemStatus.APPROVED or item.is_legacy:
        return False
    return Placement.objects.filter(live_placements_q(clock.today()), pk=placement_id).exists()


def _record_failure(
    snapshot: Snapshot, item: ReviewItem, *, code: str, message: str, at: datetime, http_status: int | None = None
) -> None:
    snapshot.status = CheckStatus.FAILED.value
    snapshot.finished_at = at
    snapshot.error_code = code
    snapshot.error_message = message[:500]
    snapshot.http_status = http_status
    snapshot.save(update_fields=["status", "finished_at", "error_code", "error_message", "http_status"])
    record_event(
        type=EventType.DRIFT_CHECKED,
        entity=EntityType.PLACEMENT,
        entity_id=snapshot.placement_id,  # pyrefly: ignore[missing-attribute]
        item_id=item.pk,
        payload=DriftCheckedPayload(
            placement_id=snapshot.placement_id,  # pyrefly: ignore[missing-attribute]
            snapshot_id=snapshot.pk,
            status=CheckStatus.FAILED,
            error_code=code,
            http_status=http_status,
        ),
        actor=None,
        at=at,
    )


def fail(
    *, claim: Claim, error: FetchError | None = None, code: str = "", message: str = "", clock: Clock = SYSTEM_CLOCK
) -> bool:
    """running -> failed, visibly: from a FetchError, or a code and message ("error" from the task boundary).
    Returns whether the item was reopened: the page was gone on GONE_AFTER consecutive checks (module docstring)."""
    with transaction.atomic():
        item = locked_item(claim.item_id)
        snapshot = _locked_running(claim)
        if snapshot is None:
            return False
        http_status = error.http_status if error is not None else None
        _record_failure(
            snapshot,
            item,
            code=str(error.code) if error is not None else code,
            message=error.message if error is not None else message,
            http_status=http_status,
            at=clock.now(),
        )
        if http_status not in GONE_HTTP_STATUSES:
            return False
        recent = (
            Snapshot.objects.filter(
                placement_id=claim.placement_id, status__in=(CheckStatus.SUCCEEDED.value, CheckStatus.FAILED.value)
            )
            .order_by("-requested_at", "-pk")
            .values_list("pk", "status", "http_status", "reopen_event_id")[:GONE_AFTER]
        )
        streak = gone_streak(
            CheckRow(id=pk, status=CheckStatus(status), http_status=code_, reopened=event_id is not None)
            for pk, status, code_, event_id in recent
        )
        if len(streak) < GONE_AFTER or not _at_risk(item, claim.placement_id, clock):
            return False
        snapshot.reopen_event_id = reopen_item(  # pyrefly: ignore[missing-attribute]
            item_id=item.pk,
            reason=ReopenReason.DRIFT_DETECTED,
            clock=clock,
            snapshot_id=snapshot.pk,
            failed_snapshot_ids=streak,
        )
        snapshot.save(update_fields=["reopen_event"])
    return True


# --- the daily sweep and the reconciler ------------------------------------------------------------------------


def run_sweep(*, clock: Clock = SYSTEM_CLOCK) -> SweepResult:
    """Daily: request a check of every monitored, live placement with a URL on an approved item. One transaction
    per placement; a placement whose check is still in flight is skipped."""
    due = (
        Placement.objects.filter(
            live_placements_q(clock.today()),
            monitored=True,
            item__status=ItemStatus.APPROVED.value,
            item__is_legacy=False,
        )
        .exclude(url="")
        .exclude(snapshots__status__in=IN_FLIGHT)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    requested: list[int] = []
    skipped: list[int] = []
    for placement_id in list(due):
        try:
            request_check(actor=None, placement_id=placement_id, trigger=DriftTrigger.SCHEDULED, clock=clock)
        except (Conflict, NotFound):  # decide here: the placement changed under the sweep; tomorrow retries it
            logger.warning("drift sweep skipped placement_id=%d", placement_id, exc_info=True)
            skipped.append(placement_id)
            continue
        requested.append(placement_id)
    return SweepResult(requested=tuple(requested), skipped=tuple(skipped))


def reconcile(*, clock: Clock = SYSTEM_CLOCK) -> ReconcileResult:
    """Running longer than STUCK_AFTER (the worker died) -> failed "stuck". Pending longer than STUCK_AFTER (the
    enqueue was lost) -> enqueued again, until LOST_AFTER, then failed too."""
    now = clock.now()
    stale = Q(status=CheckStatus.RUNNING.value, started_at__lt=now - STUCK_AFTER) | Q(
        status=CheckStatus.PENDING.value, requested_at__lt=now - LOST_AFTER
    )
    failed: list[int] = []
    for snapshot_id in Snapshot.objects.filter(stale).order_by("pk").values_list("pk", flat=True):
        with transaction.atomic():
            item_id = Snapshot.objects.filter(pk=snapshot_id).values_list("placement__item_id", flat=True).get()
            item = locked_item(item_id)
            snapshot = Snapshot.objects.select_for_update().filter(pk=snapshot_id, status__in=IN_FLIGHT).first()
            if snapshot is None:
                continue
            _record_failure(snapshot, item, code="stuck", message="The check didn't finish. Try again.", at=now)
        failed.append(snapshot_id)
    lost = Snapshot.objects.filter(
        status=CheckStatus.PENDING.value, requested_at__lt=now - STUCK_AFTER, requested_at__gte=now - LOST_AFTER
    )
    requeued = list(lost.order_by("pk").values_list("pk", flat=True))
    for snapshot_id in requeued:
        enqueue(snapshot_id)
    return ReconcileResult(failed=tuple(failed), requeued=tuple(requeued))
