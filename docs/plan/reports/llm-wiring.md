# Report: LLM pre-review wiring (workstream D phase 2, issue #5)

Branch `wsD/llm-wiring`. Plan: `docs/plan/llm-wiring.md`. Review with resolutions: `docs/plan/reviews/llm-wiring.md`.

Executed natively. Every task wrote through the same `checks/prereview.py` state machine and the same test file,
so parallel implementers would have collided on both.

## What shipped

Every submission, resubmission and new round now gets an AI check, and `llm_check_status` leaves `pending`, so
Approve stops refusing with `ai_check_pending`.

| Piece | Where | What it does |
|---|---|---|
| Outbox handler `checks.llm_prereview` | `checks/handlers.py` | On ITEM_SUBMITTED, ITEM_RESUBMITTED, ITEM_NEW_ROUND_STARTED: a pending LLM `CheckRun`, LLM_CHECK_REQUESTED, and the task enqueued once the receipt commits |
| Lifecycle service | `checks/prereview.py` | `request_check`, `claim`, `attempt`, `requeue`, `fail`, `complete`, `reconcile`, `retry_check` |
| Celery task | `checks/tasks.py` `checks.run_llm_prereview(version_id)` | Claim, one model call, outcome. `bind=True` + `self.retry`, backoff 30/60/120 s, soft limit 280 s, hard 300 s. The budget (4 calls, one retry after unreadable output) is counted on the run |
| Reconciliation | `checks.reconcile_llm_checks`, beat every 120 s | Requested > 30 min ago and unfinished → `failed`. `running` > 10 min → `failed`. Both use code `stuck`. `pending` > 10 min → enqueued again. A reviewable item `pending` with no AI run → requested |
| Retry | `POST /items/{id}/llm-check/retry` → 202 `ItemRowOut` | Reviewer or lead, only from `failed`, only while submitted / in_review / needs_rereview |
| Settings | `config/settings/base.py` | `ANTHROPIC_API_KEY` (str or None), `ANTHROPIC_MODEL`; test settings force the key to None |
| Schema | `checks/migrations/0004_llm_runs.py` | `CheckRun.attempts`, `invalid_outputs`, `requested_at`; CHECK `finding_llm_is_warning` |

### State machine

```
request_check (handler / retry)   run pending    item pending*   LLM_CHECK_REQUESTED (retry flag, actor)
claim (task)                      run running    item running*   LLM_CHECK_STARTED (attempt n)
review_copy                       no transaction open
  complete                        run succeeded  item succeeded* LLM_CHECK_SUCCEEDED; recount open findings*
  requeue (retryable, budget left) run pending   item stays running   LLM_CHECK_RETRY_SCHEDULED (error, countdown)
  fail                            run failed     item failed*    LLM_CHECK_FAILED (code, plain reason)
* only if the run's version is still item.current_version, checked under the item row lock
```

- **Each step is a short transaction.** The model call happens with none open, because an open transaction holds
  back the outbox dispatcher's `pg_snapshot_xmin` horizon for its whole duration.
- **Idempotency is the claim.** `claim` locks the item row (lock order as in `reviews.assignment`), then the
  version's latest LLM run, and acts only on `pending`. A duplicate delivery, an acks_late redelivery, or a
  reconciler re-enqueue racing the original returns `noop`. Findings also go through `persist_findings`, which
  dedupes on `(source, rule_id, span)`.
- **Failure mapping** (`core.domain.LlmFailureCode`):

| Outcome | Status | Code |
|---|---|---|
| `LlmUnavailable(retryable)`, retries left | requeue, Celery retry | — |
| `LlmUnavailable(retryable)`, 4th attempt | failed | `provider_unavailable` |
| `LlmUnavailable(retryable=False)` | failed after 1 call | `provider_refused` |
| `output_valid=False` once | retry, countdown 0 | — |
| `output_valid=False` twice | failed | `invalid_output` |
| no API key | failed | `not_configured` |
| `SoftTimeLimitExceeded` | failed | `timeout` |
| any other exception (task top level, logged) | failed | `error` |
| reconciler: running > 10 min | failed | `stuck` |

- **A stale result** (the version was replaced while the call ran) stores its findings on the version it was
  computed for. The item's status and count are left alone, and the event says `current: false`.
- **A late result after the reconciler already failed the run** is dropped and logged, so each run has one terminal
  transition.
- **No item stays `pending` or `running` forever.** Each hole has its own fix:

| Hole | Fix |
|---|---|
| Worker death | `stuck` after 10 min |
| Lost message | enqueued again; the budget continues on the run |
| Lost retry chain, or a run that never ends | `stuck` 30 min after the request |
| Handler never ran (items submitted before this deploy) | the reconciler requests a check |

  The handler skips a version that was already replaced when the event was delivered.
- **Carry-forward:** a dismissed AI finding with the same rule and quote as on an earlier version is created
  dismissed and marked carried (`persist_findings`). Temperature is fixed at 1, so quotes vary run to run and this
  matches less often than it does for code findings.
- **Observability (§6.4):** LLM_CHECK_SUCCEEDED carries `model, ruleset_key, prompt_version, latency_ms,
  input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, dropped_by_reason, adjustments_by_kind,
  attempt, current`. The same values are logged on one line. `CheckRun` stores model, tokens, findings and
  dropped counts.

## Rulings made here (reversible)

- Ruling: with no API key the check ends `failed` (code `not_configured`, "The AI check didn't run: no Anthropic API key is configured here."), not `skipped` — E's gate passes `skipped`, and `create_version(origin=FAST_TRACK)` and legacy imports rely on that (ruling 4: no override for fast-track), so a `skipped` that demanded an override would break F's bulk fast-track; `failed` gets the override gate and the Retry action with no change to E's gate, F, or the frontend enum — cost if wrong: a new `CheckStatus` member plus one gate branch in `reviews/decisions.py`. **This deviates from the brief's literal "skipped"; orchestrator to confirm.**
- Ruling: AI findings are always `warning` (orchestrator ruling, enforced here) — `complete` coerces severity and the `finding_llm_is_warning` CHECK constraint backs it — cost if wrong: drop a constraint.
- Ruling: unreadable output retries once (phase 1 item 2), as a Celery retry, so each task execution is one model call under the 300 s hard limit — cost if wrong: one counter.
- Ruling: retry only while the item is submitted, in_review or needs_rereview — findings on an approved version can't be triaged — cost if wrong: one condition.
- Ruling: the AI check gives up 30 min after the request (GIVE_UP_AFTER; the longest legitimate chain is ~23.5 min) — bounds every retry chain and lost message so the gate can't deadlock — cost if wrong: a constant.
- Ruling: a version already replaced when its event is delivered gets no AI check — its result could never reach the gate — cost if wrong: one condition in the handler.
- Ruling: a result that arrives after the reconciler failed its run is discarded — one terminal transition per run, and the reviewer may already have approved with an override — cost if wrong: the findings of one slow call.
- Ruling: no result cache yet (spec §7, phase 1 item 4). The CheckRun stores `content_sha256` and `ruleset_key = LLM_RULESET_VERSION/PROMPT_VERSION/ENGINE_VERSION/model`, so reuse is a follow-up. When it's built, the key must hash the full rule context (product, channel, markets, partner type, attachment kinds, current terms), not just the text — cost: one extra ~$0.00025 call when a new round copies the text unchanged.
- `to_finding` is moot. `checks/llm/screen.py` builds AI drafts with `source=LLM`, so `checks/engine/rule.py` is untouched.

## Shared-file touches

All are additive:

- `core/domain.py`: `EventType.LLM_CHECK_STARTED`, `EventType.LLM_CHECK_RETRY_SCHEDULED` and `LlmFailureCode`.
- `audit/payloads.py`:
  - `LlmCheckStartedPayload` and `LlmCheckRetryScheduledPayload` are new.
  - Defaulted fields were added to the Requested, Succeeded and Failed payloads, so old events still parse.
- `config/settings/base.py` and `test.py`.
- `config/tests/test_contract.py`: the retry stub is removed.
- `partners/tests/test_api.py`: a fixture created a *blocking* LLM finding, which the new constraint refuses. It is
  now a warning; the assertions are unchanged.
- No `reviews/**` changes.

## Verification

Run from `backend/` with the brief's env and test DB suffix `wsD2`:

```
$ uv run pytest -q
1242 passed, 2 deselected
$ uv run --group lint ruff check . && uv run --group lint ruff format --check .
All checks passed! / 256 files already formatted
$ uv run --group typecheck pyrefly check
0 errors
$ manage.py makemigrations --check --dry-run
No changes detected
$ manage.py check --fail-level WARNING
System check identified no issues
$ make schema   (then frontend) npm run typecheck / test:run / lint / format:check
tsc ok; 145 passed; eslint ok; prettier ok
```

### Tests

The tests are in `checks/tests/test_prereview.py`, 34 of them. Each uses the `GenericFakeChatModel` fakes from
phase 1 through the `checks.tasks.model_factory` seam, and Celery runs eagerly, so `self.retry` re-runs
synchronously. They cover:

- **Handler registration and requests:** the handler is registered for exactly three event types.
- **Exclusions:** reviewer-edit and fast-track versions get no AI delivery, checked through
  `dispatch_pending`.
- **Happy path through to Approve:** findings are stored with source llm, span, quote, citation and fix. The
  run's tokens and model are recorded, the event payload is checked, and the open count includes the new finding.
- **Severity:** AI findings are always warnings, both by coercion and by DB constraint.
- **Dropped findings:** counted by reason.
- **Provider errors:**
  - Retry then success.
  - Retries exhausted → failed, and Approve then needs `llm_override_reason`.
  - Non-retryable → failed after one call.
- **Unreadable output:**
  - Twice → failed.
  - Once → retried, then succeeded.
- **No key:** failed with `not_configured`.
- **Settings model:** the configured name and key reach the model.
- **Unexpected error:** failed with `error`.
- **Stale version:** the findings land on v1 and the item stays pending for v2.
- **Idempotent re-delivery:** a second delivery is a noop, with no duplicate findings and no second event.
- **Carried dismissal:** carried into the resubmitted version.
- **Reconciliation:**
  - Stuck after 11 min → failed. A 5-minute-old run is untouched.
  - A stuck run on a replaced version fails the run but leaves the item alone.
  - A stale pending run is enqueued again exactly once.
- **Fixes from the review:**
  - A re-enqueued run continues its budget.
  - A lost retry message ends `failed`.
  - A pending item with no run gets one.
  - The soft time limit ends in `timeout`.
  - A late result is dropped.
  - Concurrent claims (two threads) take the run once.
  - No transaction is open during the model call (transactional DB).
  - A version replaced before delivery gets no check.
- **Retry service and endpoint:** 202, 409 `llm_check_not_failed`, 403 for a marketer, 409 `invalid_transition`
  once decided.

**Mutation checks** were each run, seen failing, then reverted:

| Mutation | Tests that failed |
|---|---|
| Drop the warning coercion | the severity test |
| Drop the current-version guard | the stale-version and stale-stuck tests |
| Let `claim` take non-pending runs | the idempotency test |
| Drop the invalid-output retry | the two invalid-output tests |
| Ignore the run's budget | the budget test |
| Drop the 30-minute give-up | the lost-retry-message test |
| Drop the request for orphaned pending items | the orphan test |
| Wrap the call in `atomic()` | the no-transaction test |

**Not run: the live smoke test.** It's `checks/tests/test_prereview_live.py`, behind the `live` marker. It submits
an item, delivers the handler, runs the task against the real API, and asserts `succeeded`, tokens > 0 and
latency > 0. Test settings blank the key, so it reads it from `env`. Run it from `backend/` with
`uv run pytest -m live checks/tests/test_prereview_live.py`.

## For other workstreams

- **I (frontend):**
  - The failure reason isn't on the item row. It's in history, under LLM_CHECK_FAILED's `error` and `code`.
  - Show the Retry action (`retryLlmCheck`) when `llm_check_status == failed`.
  - `code == not_configured` deserves its own copy: retrying won't help until a key exists.
  - `running` and `pending` both mean "wait".
  - Code-point offsets still need UTF-16 conversion.
- **Ops:** beat must run `checks.reconcile_llm_checks`. It's in `CELERY_BEAT_SCHEDULE`. Without it, a worker
  death leaves the item `running` until someone notices.
- **Orchestrator (deploy wave):** should prod refuse to boot without `ANTHROPIC_API_KEY`? The reviewer suggests it, and so did the llm-core report. Today a missing key turns every check into `failed`/`not_configured` plus an override. That's loud, but it doesn't stop a deploy.
- **Dev:** with no key, every new item's AI check fails within seconds of dispatch. Approve then works with an
  override reason.
