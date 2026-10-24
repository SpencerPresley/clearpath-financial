"""Celery entry points for the AI pre-review. Process boundaries (spec §6.1): every failure ends in visible state
on the run and the item (`failed` with a plain reason), never a silent gap.

`run_llm_prereview` is keyed by version id and idempotent: it acts only if it can claim the version's pending run,
so a duplicate delivery, a redelivery after a worker death, or a reconciler re-enqueue racing the original does
nothing. Retries go through `self.retry` (not `autoretry_for`), so running out of them still records `failed`.
"""

import logging
import time
from typing import Final

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded

from checks import prereview
from core.clock import SYSTEM_CLOCK, Clock
from core.domain import LlmFailureCode

logger = logging.getLogger(__name__)

MAX_RETRIES: Final = 3  # 4 attempts in all; the Anthropic SDK retries each call 3 more times itself
# One attempt is one call: at worst 4 x 60 s SDK attempts plus backoff (~255 s). Soft limit fails it visibly.
SOFT_TIME_LIMIT: Final = 280
TIME_LIMIT: Final = 300

# Seams: tests hand in a scripted model and a fixed clock.
model_factory: prereview.ModelFactory = prereview.settings_model
clock: Clock = SYSTEM_CLOCK


@shared_task(
    bind=True,
    name="checks.run_llm_prereview",
    max_retries=MAX_RETRIES,
    soft_time_limit=SOFT_TIME_LIMIT,
    time_limit=TIME_LIMIT,
)
def run_llm_prereview(self: Task, version_id: int, invalid_outputs: int = 0) -> str:
    started = time.monotonic()
    claim = prereview.claim(version_id=version_id, clock=clock)
    if claim is None:
        logger.info("ai check noop version_id=%d (nothing pending)", version_id)
        return "noop"
    logger.info("ai check start version_id=%d run_id=%d attempt=%d", version_id, claim.run_id, claim.attempt)
    try:
        outcome = prereview.attempt(
            claim=claim,
            can_retry=self.request.retries < MAX_RETRIES,
            invalid_outputs=invalid_outputs,
            model_factory=model_factory,
            clock=clock,
        )
    except SoftTimeLimitExceeded:
        prereview.fail(claim=claim, code=LlmFailureCode.TIMEOUT, error=prereview.TIMEOUT_MESSAGE, clock=clock)
        return "failed"
    except Exception:
        logger.exception("ai check error version_id=%d run_id=%d", version_id, claim.run_id)
        prereview.fail(claim=claim, code=LlmFailureCode.ERROR, error=prereview.ERROR_MESSAGE, clock=clock)
        return "failed"
    logger.info(
        "ai check %s version_id=%d run_id=%d attempt=%d duration_ms=%d",
        outcome.kind,
        version_id,
        claim.run_id,
        claim.attempt,
        (time.monotonic() - started) * 1000,
    )
    if outcome.kind == "retry":
        raise self.retry(
            args=(),
            kwargs={"version_id": version_id, "invalid_outputs": outcome.invalid_outputs},
            countdown=outcome.countdown,
        )
    return outcome.kind


@shared_task(name="checks.reconcile_llm_checks")
def reconcile_llm_checks() -> int:
    """Beat, every 2 minutes: stuck runs fail, lost ones are enqueued again. Returns runs touched."""
    result = prereview.reconcile(clock=clock)
    return len(result.failed) + len(result.requeued)
