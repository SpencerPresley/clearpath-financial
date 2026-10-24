# LLM pre-review wiring (workstream D phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every submission, resubmission and new round gets an AI pre-review whose result moves
`ReviewItem.llm_check_status` off `pending`, so Approve stops refusing with `ai_check_pending`.

**Architecture:** An outbox handler (`checks.llm_prereview`) creates a pending LLM `CheckRun` for the event's
version, records LLM_CHECK_REQUESTED, and enqueues a Celery task on commit. The task runs one attempt as three
short transactions around a call made with no transaction open: claim (pending → running), `review_copy`, then
complete / requeue / fail under the item row lock. A beat task fails runs stuck in `running` and re-enqueues
pending runs whose message was lost.

**Tech Stack:** Django 6, django-ninja, Celery 5.6 (eager in tests), langchain-core `GenericFakeChatModel`
(phase 1's `checks/llm/tests/fakes.py`), Postgres.

**Spec:** `docs/spec.md` §4.2 rulings 3-4, §6.1, §6.4, §7; `docs/plan/reports/llm-core.md` "What phase 2 must
wire"; `docs/plan/reports/review-workflow.md` "D2"; `docs/plan/reports/foundation.md` "Events and the outbox".

## Global Constraints

- Handler name `checks.llm_prereview`, registered on ITEM_SUBMITTED, ITEM_RESUBMITTED, ITEM_NEW_ROUND_STARTED
  only. Never VERSION_CREATED (reviewer edits carry vN's result; fast-track is `skipped`).
- No DB transaction is open while the model is called (the outbox cursor waits on `pg_snapshot_xmin`).
- `llm_check_status` is written only when the run's version is still `item.current_version`, checked under the
  item row lock (`reviews.assignment.locked_item`).
- `output_valid=False` is never `succeeded`.
- Model from `settings.ANTHROPIC_MODEL`, key from `settings.ANTHROPIC_API_KEY`, passed explicitly to
  `get_review_model(..., api_key=...)`.
- Findings go through `checks.services.persist_findings` (dedupe + carried dismissals), then
  `recount_open_findings`. `checks/services.py` is otherwise untouched (E's follow-ups edit it).
- Payload changes are additive with defaults; one new EventType `LLM_CHECK_STARTED = "llm_check.started"`.
- User-facing reasons are plain sentences, no "violation"/"non-compliant" (spec §5.4).
- Env for every backend command: `CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=clearpath-dev
  POSTGRES_PORT=55432 REDIS_URL=redis://localhost:56379/0 CLEARPATH_TEST_DB_SUFFIX=wsD2`.

## Rulings made in this plan

- **No API key → `failed` (code `not_configured`), not `skipped`.** E's gate passes `skipped`, and
  `create_version(origin=FAST_TRACK)` plus legacy imports rely on that (ruling 4: fast-track needs no override).
  Making `skipped` demand an override breaks F's bulk fast-track. `skipped` = the check isn't needed;
  `failed` = it was needed and didn't happen, and the override reason records a human taking responsibility.
  The gate, F and the frontend enum stay unchanged; retry works once a key is configured.
- **`to_finding` is moot.** `checks/llm/screen.py` builds LLM drafts with `source=LLM` itself; `rule.py` untouched.
- **A late result after the reconciler failed the run is discarded** (logged): one terminal transition per run.
- **Invalid output retries once** (phase 1 item 2) through a Celery retry with `invalid_outputs=1`, so each task
  execution makes exactly one model call and fits under the 300 s hard limit.
- **Retry endpoint only from `failed`, only while the item is reviewable** (`submitted|in_review|needs_rereview`):
  new findings on an approved version would be untriageable.
- **No result cache yet.** The CheckRun stores the key (`content_sha256`, `ruleset_key =
  LLM_RULESET_VERSION/PROMPT_VERSION/ENGINE_VERSION/model`) so reuse on identical text is a follow-up.

## Review Focus

1. Duplicate delivery (acks_late, redelivery, reconciler requeue racing the original): one model call per
   claim, no duplicate findings, one SUCCEEDED event → Task 3 `test_second_delivery_is_a_noop`.
2. Resubmission while v1's call is in flight: v1 gets its findings, v2's `pending` is untouched → Task 3
   `test_stale_version_keeps_findings_but_not_status`.
3. Worker death mid-call: item must not stay `running` forever → Task 4 `test_stuck_running_flips_to_failed`.
4. Lost enqueue (Redis flushed): pending run never claimed → Task 4 `test_stale_pending_is_requeued`.
5. Reviewer already dismissed the same LLM finding on v1 and the marketer resubmits unchanged text → carried
   dismissal on v2 → Task 3 `test_dismissal_carries_to_the_next_version`.

---

### Task 1: Settings, payloads, prereview state machine (no model call yet)

**Files:**
- Modify: `backend/config/settings/base.py` (`ANTHROPIC_API_KEY: str | None`, `ANTHROPIC_MODEL: str`, beat entry
  `"reconcile-llm-checks": {"task": "checks.reconcile_llm_checks", "schedule": 120.0}`)
- Modify: `backend/core/domain.py` (`EventType.LLM_CHECK_STARTED`)
- Modify: `backend/audit/payloads.py`
- Create: `backend/checks/prereview.py`, `backend/checks/handlers.py`, `backend/checks/errors.py`
- Test: `backend/checks/tests/test_prereview.py`

**Interfaces (Produces):**
```python
# audit.payloads (additive)
LlmCheckRequestedPayload(version_id, check_run_id: int | None = None, retry: bool = False)
LlmCheckStartedPayload(version_id, check_run_id, attempt: int)
LlmCheckSucceededPayload(... existing ..., model="", ruleset_key="", prompt_version="", latency_ms=0,
    input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_creation_tokens=0,
    dropped_by_reason: dict[str, int] = {}, adjustments_by_kind: dict[str, int] = {}, attempt=1,
    current=True)          # current=False: computed for a version that was replaced meanwhile
LlmCheckFailedPayload(... existing ..., code: FailureCode = "error", attempt=1, current=True)

# checks.prereview
FailureCode = Literal["not_configured", "provider_unavailable", "provider_refused", "invalid_output",
                      "stuck", "timeout", "error"]
STUCK_AFTER: Final = timedelta(minutes=10)
def ruleset_key(model_name: str) -> str
def request_check(*, version: Version, actor: User | None, clock: Clock, retry: bool = False) -> CheckRun
    # caller's txn, item locked by caller; pending CheckRun, item pending if current, REQUESTED event,
    # transaction.on_commit(enqueue(version.pk))
enqueue: Callable[[int], None]   # module-level seam; default delays checks.run_llm_prereview
@dataclass(frozen=True) class Claim: run_id: int; version_id: int; item_id: int; attempt: int
def claim(*, version_id: int, attempt: int, clock: Clock) -> Claim | None   # None: nothing pending
def requeue(*, claim: Claim, error: str, clock: Clock) -> None    # run -> pending; item stays running
def fail(*, claim: Claim, code: FailureCode, error: str, clock: Clock) -> None
def complete(*, claim: Claim, result: LlmReviewResult, clock: Clock) -> None
# checks.errors
class LlmCheckNotFailed(Conflict): code = "llm_check_not_failed"
```

- [ ] Step 1: tests — `test_handler_is_registered_only_for_submission_events` (`REGISTRY.get("checks.llm_prereview")
  .event_types == {ITEM_SUBMITTED, ITEM_RESUBMITTED, ITEM_NEW_ROUND_STARTED}`); `test_handler_requests_a_check`
  (deliver on a real submit's event inside `django_capture_on_commit_callbacks(execute=True)` with `enqueue`
  monkeypatched to a recorder: one pending llm CheckRun, LLM_CHECK_REQUESTED, recorder == [version_id]);
  `test_claim_moves_pending_to_running_once` (second claim → None; item running; one STARTED event attempt=1);
  `test_fail_on_current_version` (item failed, FAILED payload code/error); payload defaults parse old events.
- [ ] Step 2: run → FAIL (module missing).
- [ ] Step 3: implement. `claim` locks the item, then `select_for_update` the latest llm run for the version.
- [ ] Step 4: run → PASS. Step 5: commit.

### Task 2: The attempt and the Celery task

**Files:** Create `backend/checks/tasks.py`; extend `checks/prereview.py`; test `checks/tests/test_prereview_task.py`.

**Interfaces:**
```python
type ModelFactory = Callable[[], BaseChatModel | None]
def settings_model() -> BaseChatModel | None      # None when no key
@dataclass(frozen=True) class AttemptOutcome: kind: Literal["noop","succeeded","failed","retry"];
    countdown: int = 0; invalid_outputs: int = 0
def run_attempt(*, version_id: int, attempt: int, can_retry: bool, invalid_outputs: int,
                model_factory: ModelFactory, clock: Clock) -> AttemptOutcome
# checks.tasks
MAX_RETRIES = 3; backoff countdown = 30 * 2**retries (30, 60, 120)
model_factory: ModelFactory = prereview.settings_model      # test seam (monkeypatch)
@shared_task(bind=True, name="checks.run_llm_prereview", max_retries=3, soft_time_limit=280, time_limit=300)
def run_llm_prereview(self, version_id: int, invalid_outputs: int = 0) -> str
@shared_task(name="checks.reconcile_llm_checks") def reconcile_llm_checks() -> int
```
Context: `rule_context(version=..., clock=...)`; code findings `checks.engine.run_code_checks(ctx).findings`.
Error mapping: `LlmUnavailable(retryable)` + can_retry → requeue + retry; retryable exhausted →
`provider_unavailable`; non-retryable → `provider_refused`; `output_valid=False` with `invalid_outputs == 0` and
can_retry → retry countdown 0, else `invalid_output`; factory None → `not_configured`; task top level:
`SoftTimeLimitExceeded` → `timeout`, other `Exception` → `error` (logged).

- [ ] Tests (fake model via `checks.llm.tests.fakes`): happy path (findings source=llm, span/quote/citation/fix,
  CheckRun succeeded with model/tokens, item succeeded, open count includes them, SUCCEEDED payload with usage,
  latency, model, dropped_by_reason); retry-then-success through `run_llm_prereview.delay` (factory pops
  RaisingModel(529), then fake report); exhausted retries → failed, 4 calls; non-retryable → failed after 1 call;
  invalid twice → failed `invalid_output`; invalid then valid → succeeded; no key → `not_configured`;
  approve after success passes the gate; approve after failure needs `llm_override_reason`.
- [ ] Run → FAIL; implement; run → PASS; commit.

### Task 3: Stale version, idempotency, carry-forward, dispatch exclusions

- [ ] Tests in `test_prereview_task.py`: `test_stale_version_keeps_findings_but_not_status` (claim v1; resubmit →
  v2 pending; complete v1 → findings on v1, item still pending, SUCCEEDED `current=False`);
  `test_second_delivery_is_a_noop` (task twice → one finding set, one SUCCEEDED, second returns "noop");
  `test_dismissal_carries_to_the_next_version`; `test_reviewer_edit_and_fast_track_get_no_llm_delivery`
  (`dispatch_pending(enqueue=recorder)` after `create_version(origin=REVIEWER_EDIT|FAST_TRACK)`: no
  `checks.llm_prereview` delivery). Fix whatever fails; commit.

### Task 4: Reconciliation

`def reconcile(*, clock: Clock) -> ReconcileResult(failed: tuple[int, ...], requeued: tuple[int, ...])`:
running runs with `started_at < now - STUCK_AFTER` → `fail(code="stuck")`; pending runs older than
`STUCK_AFTER` → `enqueue(version_id)` and `started_at = now`.
- [ ] Tests: `test_stuck_running_flips_to_failed` (11 min → failed, 5 min → untouched, non-current version →
  run failed, item untouched); `test_stale_pending_is_requeued`. Implement; commit.

### Task 5: Retry endpoint, schema, live smoke, docs

- `checks.prereview.retry_check(*, actor: User, item_id: int, clock: Clock) -> None`: `require_role(actor,
  *REVIEW_ROLES)`; lock item; status in TRIAGEABLE else `InvalidTransition(action="retry_llm_check")`;
  `llm_check_status == failed` else `LlmCheckNotFailed`; `request_check(retry=True, actor=actor)`.
- `checks/api.py`: 202 `ItemRowOut` via `Status(202, get_item_row(...))`, `ERRORS`; remove the stub line from
  `config/tests/test_contract.py`.
- [ ] API tests: 202 from failed (pending, enqueued), 409 `llm_check_not_failed` from succeeded, 403 marketer.
- [ ] Live smoke `checks/tests/test_prereview_live.py` (`live` marker, skip without settings key): submit, run
  `run_attempt` with `settings_model`, assert succeeded and CheckRun tokens > 0.
- [ ] `make schema`; ruff, pyrefly, migrations check, full pytest; report `docs/plan/reports/llm-wiring.md`;
  fresh review → `docs/plan/reviews/llm-wiring.md`; PR.
