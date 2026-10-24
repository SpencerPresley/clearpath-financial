"""The AI pre-review lifecycle on a version: request, claim, call, then succeed, retry or fail.

A services module in the CLAUDE.md sense: the only writer of AI CheckRuns, of AI findings (through
`checks.services.persist_findings`) and of `ReviewItem.llm_check_status` after submission. It never approves,
and nothing the model returns reaches a status other than the check's own.

    request_check (outbox handler / retry)   pending   LLM_CHECK_REQUESTED, enqueue on commit
    claim (task)                             running   LLM_CHECK_STARTED (attempt n)
    attempt: review_copy, no transaction open
      -> complete                            succeeded LLM_CHECK_SUCCEEDED (usage, latency, model, drops)
      -> requeue (retryable, retries left)   pending   (item stays running; the task retries with backoff)
      -> fail                                failed    LLM_CHECK_FAILED (code, plain reason)
    reconcile (beat)   running > STUCK_AFTER -> failed (stuck); pending > STUCK_AFTER -> enqueued again

The item's `llm_check_status` mirrors the run only while the run's version is the item's current version,
checked under the item row lock. A run whose version was replaced meanwhile still stores its findings on that
version (the history keeps them) but leaves the item alone.

Each step is a short transaction: the model call happens with none open, because an open transaction holds back
the outbox dispatcher's snapshot horizon for its whole duration.
"""

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Final, Literal

from django.conf import settings
from django.db import transaction
from langchain_core.language_models import BaseChatModel

from accounts.models import User
from audit.payloads import (
    LlmCheckFailedPayload,
    LlmCheckRequestedPayload,
    LlmCheckStartedPayload,
    LlmCheckSucceededPayload,
)
from audit.services import record_event
from checks.engine import ENGINE_VERSION, FindingDraft
from checks.engine import run_code_checks as run_engine
from checks.errors import LlmCheckNotFailed
from checks.llm import (
    LLM_RULESET_VERSION,
    PROMPT_VERSION,
    LlmReviewResult,
    LlmUnavailable,
    get_review_model,
    review_copy,
)
from checks.models import CheckRun
from checks.services import TRIAGEABLE, persist_findings, recount_open_findings, rule_context
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import CheckStatus, EntityType, EventType, FindingSource, ItemStatus, LlmFailureCode, Severity
from core.errors import InvalidTransition
from core.permissions import REVIEW_ROLES, require_role
from reviews.assignment import locked_item
from reviews.models import ReviewItem, Version

logger = logging.getLogger(__name__)

# Longer than any attempt can run (the task's hard time limit is 300 s) and than the longest retry backoff
# (120 s), so a run older than this in `running` lost its worker, and one in `pending` lost its message.
STUCK_AFTER: Final = timedelta(minutes=10)

type ModelFactory = Callable[[], BaseChatModel | None]

_NOT_CONFIGURED: Final = "The AI check didn't run: no Anthropic API key is configured here."
_INVALID_OUTPUT: Final = "The AI's answer couldn't be read, twice."
STUCK_MESSAGE: Final = "The AI check stopped without finishing (its worker restarted)."
TIMEOUT_MESSAGE: Final = "The AI check took too long and was stopped."
ERROR_MESSAGE: Final = "The AI check hit an unexpected error."


def ruleset_key(model_name: str) -> str:
    """What an AI result was computed with (spec §7 cache key, minus the content hash stored beside it): the LLM
    rules, the prompt, the code engine (its findings are part of the input) and the model."""
    return f"{LLM_RULESET_VERSION.isoformat()}/{PROMPT_VERSION}/{ENGINE_VERSION}/{model_name}"


def settings_model() -> BaseChatModel | None:
    """The production model from settings, or None when no API key is configured (dev, CI)."""
    key = settings.ANTHROPIC_API_KEY
    if not key:
        return None
    return get_review_model(settings.ANTHROPIC_MODEL, api_key=key)


def _enqueue_task(version_id: int) -> None:
    from checks.tasks import run_llm_prereview  # noqa: PLC0415  # tasks imports this module

    run_llm_prereview.delay(version_id)


# Seam: tests replace it to observe or suppress the enqueue.
enqueue: Callable[[int], None] = _enqueue_task


def _is_current(item: ReviewItem, version_id: int) -> bool:
    return item.current_version_id == version_id  # pyrefly: ignore[missing-attribute]


def _mirror(item: ReviewItem, version_id: int, status: CheckStatus) -> bool:
    """Set the item's AI status if `version_id` is its current version. Returns whether it was."""
    if not _is_current(item, version_id):
        return False
    ReviewItem.objects.filter(pk=item.pk).update(llm_check_status=status.value)
    item.llm_check_status = status
    return True


# --- request ---------------------------------------------------------------------------------------------------


def request_check(
    *, item: ReviewItem, version: Version, actor: User | None, clock: Clock, retry: bool = False
) -> CheckRun:
    """Queue an AI check of `version`, in the caller's transaction with `item` locked: a pending CheckRun, the
    item pending (if `version` is current), LLM_CHECK_REQUESTED, and the task enqueued once this commits."""
    now = clock.now()
    run = CheckRun.objects.create(
        version=version,
        source=FindingSource.LLM,
        status=CheckStatus.PENDING,
        content_sha256=version.content_sha256,
        ruleset_key=ruleset_key(settings.ANTHROPIC_MODEL),
        started_at=now,
    )
    _mirror(item, version.pk, CheckStatus.PENDING)
    record_event(
        type=EventType.LLM_CHECK_REQUESTED,
        entity=EntityType.VERSION,
        entity_id=version.pk,
        item_id=item.pk,
        payload=LlmCheckRequestedPayload(version_id=version.pk, check_run_id=run.pk, retry=retry),
        actor=actor,
        at=now,
    )
    version_id = version.pk
    transaction.on_commit(lambda: enqueue(version_id))
    return run


def retry_check(*, actor: User, item_id: int, clock: Clock = SYSTEM_CLOCK) -> None:
    """A reviewer runs a failed AI check again on the current version. Only while the item is under review: new
    findings on an approved version couldn't be triaged."""
    require_role(actor, *REVIEW_ROLES)
    with transaction.atomic():
        item = locked_item(item_id)
        status = ItemStatus(item.status)
        if status not in TRIAGEABLE or item.current_version is None:
            raise InvalidTransition(action="retry_ai_check", from_status=status)
        check_status = CheckStatus(item.llm_check_status)
        if check_status is not CheckStatus.FAILED:
            raise LlmCheckNotFailed(status=check_status)
        request_check(item=item, version=item.current_version, actor=actor, clock=clock, retry=True)


# --- one attempt -----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    run_id: int
    version_id: int
    item_id: int
    attempt: int


def _latest_run(version_id: int) -> CheckRun | None:
    return (
        CheckRun.objects.select_for_update()
        .filter(version_id=version_id, source=FindingSource.LLM)
        .order_by("-pk")
        .first()
    )


def _item_id(version_id: int) -> int:
    return Version.objects.values_list("item_id", flat=True).get(pk=version_id)


def claim(*, version_id: int, clock: Clock) -> Claim | None:
    """Take the version's pending AI run: pending -> running, attempt + 1, LLM_CHECK_STARTED. None if nothing is
    pending (already running elsewhere, finished, or never requested): a duplicate delivery does nothing."""
    now = clock.now()
    with transaction.atomic():
        item = locked_item(_item_id(version_id))
        run = _latest_run(version_id)
        if run is None or run.status != CheckStatus.PENDING:
            return None
        run.status, run.started_at, run.attempts = CheckStatus.RUNNING, now, run.attempts + 1
        run.save(update_fields=["status", "started_at", "attempts"])
        _mirror(item, version_id, CheckStatus.RUNNING)
        record_event(
            type=EventType.LLM_CHECK_STARTED,
            entity=EntityType.VERSION,
            entity_id=version_id,
            item_id=item.pk,
            payload=LlmCheckStartedPayload(version_id=version_id, check_run_id=run.pk, attempt=run.attempts),
            actor=None,
            at=now,
        )
    return Claim(run_id=run.pk, version_id=version_id, item_id=item.pk, attempt=run.attempts)


def _locked_running(claim: Claim) -> tuple[ReviewItem, CheckRun] | None:
    item = locked_item(claim.item_id)
    run = CheckRun.objects.select_for_update().get(pk=claim.run_id)
    if run.status != CheckStatus.RUNNING:
        # The reconciler failed it while the call ran. One terminal transition per run: drop this outcome.
        logger.warning("ai check outcome dropped run_id=%d status=%s", run.pk, run.status)
        return None
    return item, run


def requeue(*, claim: Claim, error: str, clock: Clock) -> None:
    """Back to pending for the task's retry. The item stays `running`: the check is still in progress."""
    with transaction.atomic():
        locked = _locked_running(claim)
        if locked is None:
            return
        _, run = locked
        run.status, run.error, run.started_at = CheckStatus.PENDING, error, clock.now()
        run.save(update_fields=["status", "error", "started_at"])


def _fail_run(*, item: ReviewItem, run: CheckRun, code: LlmFailureCode, error: str, clock: Clock) -> None:
    now = clock.now()
    run.status, run.error, run.finished_at = CheckStatus.FAILED, error, now
    run.save(update_fields=["status", "error", "finished_at"])
    version_id: int = run.version_id  # pyrefly: ignore[missing-attribute]
    current = _mirror(item, version_id, CheckStatus.FAILED)
    record_event(
        type=EventType.LLM_CHECK_FAILED,
        entity=EntityType.VERSION,
        entity_id=version_id,
        item_id=item.pk,
        payload=LlmCheckFailedPayload(
            version_id=version_id,
            check_run_id=run.pk,
            error=error,
            code=code,
            attempt=run.attempts,
            current=current,
        ),
        actor=None,
        at=now,
    )
    logger.warning(
        "ai check failed run_id=%d version_id=%d code=%s attempt=%d current=%s",
        run.pk,
        version_id,
        code,
        run.attempts,
        current,
    )


def fail(*, claim: Claim, code: LlmFailureCode, error: str, clock: Clock) -> None:
    """The check is over without a result. Approve then needs an override reason (E's gate)."""
    with transaction.atomic():
        locked = _locked_running(claim)
        if locked is not None:
            _fail_run(item=locked[0], run=locked[1], code=code, error=error, clock=clock)


def _as_warnings(findings: Sequence[FindingDraft]) -> tuple[FindingDraft, ...]:
    # Orchestrator ruling: AI findings are warnings whatever their rule says (a DB check backs this up).
    return tuple(replace(f, severity=Severity.WARNING) for f in findings)


def complete(*, claim: Claim, result: LlmReviewResult, clock: Clock) -> None:
    """Store the findings on the claimed version (carrying identical dismissals), finish the run, and, if the
    version is still current, mark the item succeeded and recount its open findings."""
    now = clock.now()
    with transaction.atomic():
        locked = _locked_running(claim)
        if locked is None:
            return
        item, run = locked
        version = Version.objects.select_related("item").get(pk=claim.version_id)
        findings = _as_warnings(result.findings)
        persist_findings(version=version, drafts=findings, clock=clock)
        run.status, run.finished_at, run.error = CheckStatus.SUCCEEDED, now, ""
        run.findings_count, run.dropped_findings_count = len(findings), len(result.dropped)
        run.model, run.input_tokens, run.output_tokens = (
            result.model_name[:100],
            result.usage.input_tokens,
            result.usage.output_tokens,
        )
        run.save()
        current = _mirror(item, claim.version_id, CheckStatus.SUCCEEDED)
        if current:
            recount_open_findings(item_id=item.pk)
        dropped: dict[str, int] = dict(Counter(str(d.reason) for d in result.dropped))
        adjusted: dict[str, int] = dict(Counter(str(a.kind) for a in result.adjustments))
        record_event(
            type=EventType.LLM_CHECK_SUCCEEDED,
            entity=EntityType.VERSION,
            entity_id=claim.version_id,
            item_id=item.pk,
            payload=LlmCheckSucceededPayload(
                version_id=claim.version_id,
                check_run_id=run.pk,
                findings_count=len(findings),
                dropped_findings_count=len(result.dropped),
                model=result.model_name,
                ruleset_key=run.ruleset_key,
                prompt_version=result.prompt_version,
                latency_ms=result.latency_ms,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
                cache_read_tokens=result.usage.cache_read_tokens,
                cache_creation_tokens=result.usage.cache_creation_tokens,
                dropped_by_reason=dropped,
                adjustments_by_kind=adjusted,
                attempt=claim.attempt,
                current=current,
            ),
            actor=None,
            at=now,
        )
    # Spec §6.4: cost tracking. Cache reads are the only proof prompt caching engages.
    logger.info(
        "ai check succeeded run_id=%d version_id=%d model=%s input_tokens=%d output_tokens=%d cache_read=%d "
        "cache_write=%d latency_ms=%d findings=%d dropped=%s adjustments=%s attempt=%d current=%s",
        claim.run_id,
        claim.version_id,
        result.model_name,
        result.usage.input_tokens,
        result.usage.output_tokens,
        result.usage.cache_read_tokens,
        result.usage.cache_creation_tokens,
        result.latency_ms,
        len(findings),
        dropped,
        adjusted,
        claim.attempt,
        current,
    )


@dataclass(frozen=True)
class AttemptOutcome:
    kind: Literal["succeeded", "failed", "retry"]
    countdown: int = 0
    invalid_outputs: int = 0


def backoff(attempt: int) -> int:
    """Seconds before retry n+1 after attempt n: 30, 60, 120. The SDK already retried each call 3 times."""
    return 30 * 2 ** (attempt - 1)


def attempt(
    *, claim: Claim, can_retry: bool, invalid_outputs: int, model_factory: ModelFactory, clock: Clock
) -> AttemptOutcome:
    """One model call for a claimed run, and what it led to. Provider errors and unreadable output are outcomes
    here; anything else propagates to the task, which fails the run."""
    model = model_factory()
    if model is None:
        fail(claim=claim, code=LlmFailureCode.NOT_CONFIGURED, error=_NOT_CONFIGURED, clock=clock)
        return AttemptOutcome("failed")
    version = Version.objects.select_related("item__partner").get(pk=claim.version_id)
    ctx = rule_context(version=version, clock=clock)
    try:
        result = review_copy(ctx, code_findings=run_engine(ctx).findings, model=model)
    except LlmUnavailable as error:
        if error.retryable and can_retry:
            requeue(claim=claim, error=str(error), clock=clock)
            return AttemptOutcome("retry", countdown=backoff(claim.attempt), invalid_outputs=invalid_outputs)
        if error.retryable:
            code, reason = (
                LlmFailureCode.PROVIDER_UNAVAILABLE,
                f"The AI service didn't answer after {claim.attempt} tries. {error}",
            )
        else:
            code, reason = LlmFailureCode.PROVIDER_REFUSED, f"The AI service refused the request. {error}"
        fail(claim=claim, code=code, error=reason, clock=clock)
        return AttemptOutcome("failed")
    if not result.output_valid:
        # Zero findings from unreadable output must not look clean (spec §6.1): retry once, then fail.
        if invalid_outputs == 0 and can_retry:
            requeue(claim=claim, error=_INVALID_OUTPUT, clock=clock)
            return AttemptOutcome("retry", countdown=0, invalid_outputs=1)
        fail(claim=claim, code=LlmFailureCode.INVALID_OUTPUT, error=_INVALID_OUTPUT, clock=clock)
        return AttemptOutcome("failed")
    complete(claim=claim, result=result, clock=clock)
    return AttemptOutcome("succeeded")


# --- reconciliation --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconcileResult:
    failed: tuple[int, ...]  # run ids marked failed (stuck)
    requeued: tuple[int, ...]  # run ids enqueued again


def reconcile(*, clock: Clock = SYSTEM_CLOCK) -> ReconcileResult:
    """So the AI gate never deadlocks: a run still `running` after STUCK_AFTER lost its worker and fails (code
    stuck); a run still `pending` after STUCK_AFTER lost its message and is enqueued again (claiming is
    exclusive, so a late original is harmless)."""
    cutoff = clock.now() - STUCK_AFTER
    stale = CheckRun.objects.filter(source=FindingSource.LLM, started_at__lt=cutoff)
    failed: list[int] = []
    for run_id, version_id in stale.filter(status=CheckStatus.RUNNING).values_list("pk", "version_id"):
        with transaction.atomic():
            item = locked_item(_item_id(version_id))
            run = CheckRun.objects.select_for_update().get(pk=run_id)
            if run.status == CheckStatus.RUNNING and run.started_at < cutoff:
                _fail_run(item=item, run=run, code=LlmFailureCode.STUCK, error=STUCK_MESSAGE, clock=clock)
                failed.append(run_id)
    requeued: list[int] = []
    for run_id, version_id in stale.filter(status=CheckStatus.PENDING).values_list("pk", "version_id"):
        if CheckRun.objects.filter(pk=run_id, status=CheckStatus.PENDING, started_at__lt=cutoff).update(
            started_at=clock.now()
        ):
            enqueue(version_id)
            requeued.append(run_id)
    if failed or requeued:
        logger.warning("ai check reconcile failed=%s requeued=%s", failed, requeued)
    return ReconcileResult(failed=tuple(failed), requeued=tuple(requeued))
