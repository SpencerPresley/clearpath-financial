# Review: wsD/llm-wiring (LLM pre-review wiring, workstream D phase 2)

Diff reviewed: `git diff origin/main...HEAD` (commits `8cecc34`, `c09e6b6`).

**Verdict:** no Critical findings. Two Important findings share one cause: the retry budget and the stuck
detector are tracked per Celery message, not per run. Together they break the orchestrator's "the gate never
deadlocks" ruling once a message is lost after a requeue. One small reconciler change fixes both (I-1 and I-2,
see the fix under I-2). Fix that before merge. The other Important findings are a missing Event (I-3) and a
recovery hole for an item with no run (I-4).

## What I ran

| Command | Result |
|---|---|
| `uv run pytest checks -q` (env from the brief, suffix `wsD2R`) | 534 passed, 2 deselected (live) |
| `uv run pytest -q` (whole backend) | 1234 passed, 2 deselected |
| `ruff check .`, `ruff format --check .` | clean |
| `pyrefly check` | 0 errors |
| `manage.py makemigrations --check --dry-run` | No changes detected |

I also ran three throwaway experiments. They live in the scratchpad, not the repo, and use a scratch conftest
that loads `backend/conftest.py` and `reviews.tests.conftest`.

1. **No transaction during the model call.** `django_db(transaction=True)`, the real `deliver` → on_commit →
   eager task path, with a spy on `prereview.review_copy` recording `connection.in_atomic_block`. It printed
   `in_atomic_block during call: [False]`, and the item ended `succeeded`. **The invariant holds.**
2. **Two concurrent claims.** Two threads hit a barrier, then both call `prereview.claim(version_id=v)` on
   separate connections. Output: `claims: [Claim(run_id=6, ...), None]`, and there is exactly one
   LLM_CHECK_STARTED. **Claiming is exclusive.**
3. **Retry message lost after a requeue.** Steps: `claim`, then `requeue(error="529")`, then six cycles of
   `clock.advance(STUCK_AFTER + 1s)` + `reconcile` with `enqueue` sent nowhere. Output:
   `after ~1h: running pending`. Every pass returned `failed=[] requeued=[2]`. The only events were
   `['llm_check.requested', 'llm_check.started']`. This is the evidence for I-2 and I-3.

## Verified clean (checked, not assumed)

- **Transaction boundaries.** claim, requeue, fail and complete are each their own `transaction.atomic()`.
  `attempt()` (`checks/prereview.py:358-392`) calls `review_copy` with no transaction open (experiment 1). The
  handler only enqueues `on_commit` (`prereview.py:142`), so the outbox's `pg_snapshot_xmin` horizon is never
  held across the call.
- **Lock order.** Every path locks the item row first, then the CheckRun row: claim (`:190-191`), the
  `_locked_running` helper behind requeue, fail and complete (`:210-211`), the reconciler's stuck branch
  (`:413-414`), and `request_check` (caller holds the item lock, then the insert). No path takes the assignment
  advisory lock or a second item, so this is consistent with `reviews/assignment.py:11-12`. The handler takes
  the receipt's unique key (`audit/outbox.py:184`) before the item lock. Receipts are per (event, handler), so
  that can't invert against another path.
- **Status mirrored only for the current version, under the lock.** `_mirror` (`:105-111`) compares
  `current_version_id` on the row it just locked. The stale-version test and
  `test_stuck_run_on_a_replaced_version_leaves_the_item_alone` cover both sides.
- **No gate bypass.**
  - `_require_ai_done` (`reviews/decisions.py:120-131`) reads the locked item's status.
  - `complete` writes the findings, the run and the status in one transaction, so Approve can't see
    `succeeded` without the findings.
  - Approve-with-edits calls `_require_ai_done` before `create_version(REVIEWER_EDIT)` (`decisions.py:317-319`).
    A carried status therefore can never be `pending`/`running`.
  - `retry_check` only acts from `failed`. Two concurrent retries serialize on the item lock, and the second
    gets `llm_check_not_failed`.
- **`output_valid=False` is never `succeeded`.** `attempt` (`:384-390`) retries once, then fails with
  `invalid_output`. Both branches are tested.
- **AI findings are always warnings.** They're coerced in `complete` (`:270-272, 285`) and backed by the
  `finding_llm_is_warning` CHECK constraint (migration `0004`). Both are tested. All LLM `RuleSpec`s are
  already `WARNING` (`checks/llm/rules.py:62`), so the coercion is belt and braces.
- **Stale results.** Findings persist on the computed version, the item is untouched, and the payload says
  `current=False`. Tested.
- **Celery semantics.**
  - `bind=True` with `self.retry(...)` outside the `try`, so `Retry` is not swallowed by `except Exception`.
  - `can_retry` is checked before `self.retry`, so `MaxRetriesExceededError` is unreachable.
  - Celery 5.6.3's `Task.retry` re-runs eagerly under `ALWAYS_EAGER` (countdown ignored).
    `test_retries_run_out_...` proves 4 calls: the `models` fixture asserts every scripted model was used.
  - `acks_late=True` (`config/settings/base.py:209`). A redelivery after worker death finds the run `running`
    and returns `noop`, and the reconciler fails it after 10 min as `stuck`.
- **Handler registration.** ITEM_SUBMITTED, ITEM_RESUBMITTED and ITEM_NEW_ROUND_STARTED only. The
  reviewer-edit and fast-track exclusion is tested through `dispatch_pending`.

## Critical

None.

## Important

### I-1. The retry budget resets whenever the reconciler re-enqueues a run

`backend/checks/tasks.py:49` and `:39`, `backend/checks/prereview.py:419-424`.

**Mechanism.** The retry budget lives in the message, not on the run:

- `can_retry = self.request.retries < MAX_RETRIES` is per Celery chain.
- `invalid_outputs` travels as a task kwarg.
- `reconcile` re-enqueues a stale pending run with `enqueue(version_id)`, which is
  `run_llm_prereview.delay(version_id)`. That starts a fresh chain with `retries=0, invalid_outputs=0`.

`CheckRun.attempts` keeps counting, but nothing reads it as a bound.

**Scenario.**

1. A provider outage returns 529 three times. Chain A requeues the run and publishes the retry with
   `countdown=120`.
2. That ETA message is lost. This repo has a concrete way to lose it: review-workflow.md "Open risks" notes the
   broker and the cache share a Redis DB, where an `allkeys-*` eviction policy can drop broker keys.
3. After 10 min the reconciler re-enqueues. Chain B gets four more paid attempts, and the invalid-output
   allowance resets too.
4. Repeat for as long as messages keep getting lost.

Each rescue is also another full ~4 x 60 s SDK retry ladder.

The reverse case is a retry message that is late, not lost (a backlog longer than 10 min). Then chains A and B
both exist. Each claims whenever the run is back to `pending`, and each requeue schedules its own retry, so
retry messages double per failure.

**Fix.** Derive both budgets from the run row, which survives message loss and duplicate chains:

- `can_retry = claim.attempt <= MAX_RETRIES`. `Claim.attempt` is already `run.attempts` after the increment.
- Derive "already had one invalid output" from run state. Either check `run.error == _INVALID_OUTPUT` at claim
  time (and return it on `Claim`), or add a small `invalid_outputs` column.
- The kwarg can then go, and `self.retry` only carries `countdown`.
- Test: drive one run through `claim`/`requeue` four times by hand, then call the task. It must `fail` with
  `provider_unavailable`, not call the model.

### I-2. An item can show `running` indefinitely: the reconciler never fails a requeued run

`backend/checks/prereview.py:219-227` (requeue) and `:419-424` (the pending branch of reconcile).

**Mechanism.**

- `requeue` moves the run `running → pending` and deliberately leaves the item `running`.
- The reconciler fails only runs whose status is `running` (`:411`). For `pending` it only refreshes
  `started_at` and re-enqueues (`:420-423`), with no upper bound.
- `retry_check` refuses anything but `failed` (`:156`).

So once the message after a requeue is lost, the reconciler sees `pending`, re-enqueues into the same lossy
path, and resets `started_at`. Each time:

- the item still shows `running`;
- the gate keeps answering `ai_check_pending`;
- the reviewer has no Retry action (status isn't `failed`);
- nothing ever flips the item to `failed`.

Experiment 3 shows exactly this after an hour of reconciles: item `running`, run `pending`, zero failure
events. It's a direct counterexample to the orchestrator ruling: "items stuck running > 10 min must flip to
`failed` so the gate never deadlocks".

The same unbounded loop applies to a first-attempt `pending` run whose messages are never consumed, for
example a worker fleet on an old build that doesn't register `checks.run_llm_prereview`. Its item stays
`pending`.

**Fix (recommended: one reconciler change that also closes I-1).** Give a run a terminal deadline measured
from when it was *requested*, not from the overloaded `started_at`:

- Add `requested_at` to `CheckRun`, or reuse a row-creation timestamp. `started_at` is currently rewritten by
  request (`:129`), claim (`:194`), requeue (`:226`) and reconcile (`:421`), so it can't serve as one.
- In `reconcile`, any `pending` or `running` LLM run older than a hard deadline fails with code `stuck` through
  `_fail_run`. That mirrors the item to `failed` if current and writes LLM_CHECK_FAILED. A deadline of
  `3 * STUCK_AFTER` is about 30 min; the longest legitimate chain is about 4 x 300 s plus 210 s backoff,
  roughly 23 min.
- Keep re-enqueueing younger pending runs.

Test: requeue, lose every enqueue, advance past the deadline, reconcile. The item ends `failed` (code `stuck`)
and `retry_check` then works.

Alternative: have `requeue` mirror the item to `pending`. That makes the displayed state honest, but there is
still no exit, so on its own it doesn't satisfy the ruling.

### I-3. `requeue` changes state without writing an Event

`backend/checks/prereview.py:219-227`.

**Mechanism.** The run goes `running → pending` with the provider's error in `run.error`, and no Event is
written. The next claim's LLM_CHECK_STARTED (`attempt=2`) doesn't say why attempt 1 ended. `run.error` is then
overwritten by the next requeue and blanked on success (`complete`, `:287`).

So after "529, 529, success" the audit trail holds REQUESTED, STARTED×3 and SUCCEEDED. The two provider
failures, which are what a reviewer or an on-call engineer would want for a slow check, appear nowhere durable.
The repo CLAUDE.md invariant says every state change writes its state and an `Event` in one transaction.

**Fix.** Record an event in `requeue`'s transaction. Two options, both additive with defaults:

- reuse `LLM_CHECK_FAILED` with `retrying: bool = True`, plus `countdown`;
- add `LLM_CHECK_RETRY_SCHEDULED` with `{version_id, check_run_id, attempt, code, error, countdown}`.

The first is cheaper, but any consumer that treats FAILED as terminal (I's timeline, metrics) then has to check
the flag. The second is cleaner, at the cost of one EventType and one payload, plus `make schema`. I'd take the
second.

Two related gaps:

- A late outcome dropped by `_locked_running` (`:212-215`) is only logged. Its tokens were spent but are
  recorded nowhere (spec §6.4 cost tracking). Logging the usage in that branch, or recording it on the run, is
  enough.
- The reconciler's pending re-enqueue (`:420-423`) isn't a status change, so no Event is needed there.

### I-4. An item can sit `pending` with no CheckRun at all, and nothing recovers it

`backend/checks/prereview.py:404-427`, `backend/audit/outbox.py:192-218`.

**Mechanism.**

- The reconciler iterates `CheckRun` rows only.
- An item gets `pending` from `submit_item` / `_insert_version` before the handler runs.
- If the handler never produces a receipt, there is no run. Either the outbox is stuck, the handler raises, or
  the event is older than `redeliver_stale`'s 1-day `lookback`.
- The item then stays `pending` forever: the gate refuses with `ai_check_pending`, `retry_check` refuses with
  `llm_check_not_failed`, and the reconciler can't see it.

The concrete instance today is the deploy of this branch itself. Items submitted before D2 deploys have
`pending` and no run. The dispatcher already passed their events with no matching handler, since matching
happens at dispatch (`outbox.py:160`), and `redeliver_stale` only looks back one day. Nothing is deployed yet
and there's no seed data (`accounts/management/commands/` only seeds users), so this bites existing dev
databases now and any environment that runs submissions before D2.

**Fix.** Defense in depth in `reconcile`. Find items where all of these hold:

- `llm_check_status` is `pending` or `running`;
- `current_version.origin = submission`;
- there is no LLM CheckRun on the current version;
- `submitted_at < cutoff`.

For each, call `request_check(...)` under `locked_item`, the same path as the handler. A check of this kind
depends on the outbox's delivery guarantees, so it's a backstop, not a replacement. A one-off data migration
would cover the deploy case, but not the general one.

## Minor

### M-1. Two code paths named in the plan have no test

- `backend/checks/tasks.py:54-56`: `SoftTimeLimitExceeded` → `timeout`. Test by monkeypatching
  `prereview.review_copy` to raise it.
- `backend/checks/prereview.py:209-216`: a late outcome after the reconciler failed the run is dropped. This is
  the plan's own "one terminal transition per run" ruling. Test: claim, reconcile past STUCK_AFTER (now
  failed), then `complete(claim, result)`. Expect no findings, no SUCCEEDED, run still `failed`.

### M-2. Two tests don't prove what their names claim

- `test_second_delivery_is_a_noop` (`test_prereview.py:477-489`) delivers the duplicate *after* the first
  finished. The dangerous case is a duplicate *while running* (acks_late redelivery, reconciler racing the
  original). Experiment 2 is that test: two threads with a barrier, `django_db(transaction=True)`. Add it.
- No test proves "no transaction open during the model call". Every test runs inside pytest-django's wrapping
  transaction, so `in_atomic_block` is always True there. Experiment 1 is the missing test: transactional db, a
  spy asserting `not connection.in_atomic_block`. Without it, a later refactor that wraps `attempt` in
  `atomic()` passes CI.

### M-3. A model call is spent on a version that's already stale when requested

`backend/checks/handlers.py:22-29`, `prereview.py:117-143`.

The outbox runs every 2 s, but a resubmit, withdraw or reject can land before delivery. In that case
`request_check` creates a pending run and enqueues the call even though `_is_current` is already False. The
result is a paid call whose findings land on a superseded version.

Fix: in `request_check`, if the version isn't current (or the item isn't in a status where the check matters),
don't enqueue. Recording a REQUESTED/FAILED pair or nothing is your call. Keeping stale results that were *in
flight* is the ruling; *starting* one isn't required by it.

### M-4. AI findings can land on a version whose item already left review

`prereview.py:275-297`.

Request changes and Reject don't wait for the AI check (spec §4.2 ruling 3). If the call finishes afterwards,
`current` is still True (same version), so the item gets `succeeded`, new open AI findings, and a recount while
it sits in `changes_requested`/`rejected`. That's a status where triage is refused (`TRIAGEABLE`).

This is arguably useful, since the marketer sees the AI's notes. But it's the same "untriageable findings"
concern `retry_check`'s docstring (`:147-148`) cites to refuse retries. Pick one rule and state it. If the
findings should stay, nothing to change except the docstring.

### M-5. Spec §7 says checks don't re-run for identical text; the branch always re-runs

The plan defers this ("No result cache yet") and stores the key. Note the cost: every unchanged resubmission
and every new round makes a full model call. The `test_dismissal_carries_to_the_next_version` test does exactly
that.

When it's built, the key must include more than `content_sha256 + ruleset_key`. The LLM input also depends on
product, channel, markets, partner type, attachment kinds and the current terms (`rule_context`). Reusing a
result on equal text alone would be wrong after a terms change. Hash the rendered `RuleContext`.

### M-6. Observability gaps against spec §6.4 ("every Celery task logs its start, outcome, and duration")

- `run_llm_prereview` logs duration only on the normal path (`tasks.py:61-68`). The `noop`, `timeout` and
  `error` returns log no duration.
- `reconcile_llm_checks` (`tasks.py:78-82`) logs only when it touched something, with no start or duration.
- No log line carries the event id. The handler knows `event.id`; passing it to the task (or logging it in the
  handler with the version id) links the outbox delivery to the call.

### M-7. `started_at` is overloaded

Request (`:129`), claim (`:194`), requeue (`:226`) and reconcile (`:421`) all write it. Once a run has retried,
`finished_at - started_at` is neither queue time nor call time. Fold this into the `requested_at` fix in I-2.

### M-8. The `not_configured` deviation is endorsed, but list one more deviation

`prereview.py:83-88`, `config/settings/base.py:199-204`.

With no key the check ends `failed` (`not_configured`) rather than `skipped`, and I agree:

- `skipped` means "not needed". Fast-track (`reviews/versions.py:57-58`) and legacy imports
  (`imports/services.py:382`) rely on the gate passing it.
- Using `skipped` for "needed but didn't happen" would silently disable the AI gate in an environment that lost
  its key. That's the worse failure for a compliance tool.
- `failed` makes it loud on the first item and records a human taking responsibility.
- review-workflow.md "Open risks" explicitly left this to D.
- The cost is real but acceptable: every dev and CI approval, Playwright flows and L's demo seed included,
  needs an override reason or a scripted model.

The deviation the plan doesn't list: llm-core.md "What phase 2 must wire" §7 says "validate the key at
startup", and the branch validates at call time. For dev that's the right call. For prod, add a fail-fast in
`config/settings/prod.py` (refuse to boot without `ANTHROPIC_API_KEY`), so a prod key loss stops the deploy
instead of turning every check into an override.

Small polish: the no-key path still claims (writes LLM_CHECK_STARTED `attempt=1`) before failing. You could
fail inside `request_check` and skip the Celery round trip, but the current shape keeps one code path.

### M-9. Nits

- `retry_check` raises `InvalidTransition(action="retry_ai_check")` (`prereview.py:154`), but the plan says
  `retry_llm_check`. The user-facing message reads "Can't retry ai check an item…", which is fine. Just pick one
  for the frontend's `details.action`.
- `self.retry` failing to publish (broker down) becomes Celery `Reject(requeue=False)` after `requeue` already
  committed `pending`. Recovery relies on the reconciler. That's fine by design once I-2's deadline exists.

## Resolutions (implementer)

| Finding | Resolution |
|---|---|
| I-1 retry budget resets | Fixed. The budget lives on the run: `CheckRun.attempts`, the new `invalid_outputs`, `can_retry = claim.attempt < MAX_ATTEMPTS (4)`. The task no longer carries counters in its message. Test: `test_a_reenqueued_run_continues_its_retry_budget` (fails if `can_retry` ignores the run) |
| I-2 `running` forever after a lost retry message | Fixed. The run has an immutable `requested_at`. The reconciler fails any pending or running run requested more than `GIVE_UP_AFTER = 30 min` ago (code `stuck`, "The AI check didn't finish within 30 minutes."), before it requeues anything. Test: `test_a_lost_retry_message_ends_failed` (fails without the give-up step) |
| I-3 `requeue` writes no Event | Fixed. New `EventType.LLM_CHECK_RETRY_SCHEDULED` with payload `(version_id, check_run_id, attempt, error, countdown_s)`. Asserted in `test_retryable_error_then_success`. A late result dropped after the reconciler failed the run is still only logged, deliberately: the run already has its terminal event |
| I-4 `pending` item with no run | Fixed. Reconciler step 4 finds reviewable items still `pending` whose current submission version has no AI run after `STUCK_AFTER`, and calls `request_check`. Test: `test_pending_item_without_a_run_gets_one` (fails without the step) |
| M-1 untested paths | Added `test_soft_time_limit_fails_with_timeout` and `test_a_result_after_the_reconciler_failed_the_run_is_dropped` |
| M-2 tests that don't prove their names | Added `test_concurrent_claims_take_the_run_once` (two threads, a barrier, transactional DB) and `test_no_transaction_is_open_during_the_model_call` (transactional DB, a spy on `connection.in_atomic_block`; fails when the call is wrapped in `atomic()`) |
| M-3 call spent on a version stale at delivery | Fixed in the handler: a version that's no longer current gets no run and no call. Test: `test_a_version_replaced_before_delivery_gets_no_check` |
| M-4 findings after the item left review | Kept on purpose: the marketer sees the AI's notes for the next version. `retry_check`'s docstring now states the distinction (an in-flight check lands; starting a new one after a decision only spends money) |
| M-5 result cache | Deferred, as the plan says. The report now records that the key must hash the full rule context, not just the text |
| M-6 logging | The task logs its outcome and duration on every path after a claim. The reconciler logs every run with its duration. The handler logs `event_id`, `version_id` and `run_id` |
| M-7 `started_at` overloaded | `requested_at` holds the request time. `started_at` is documented as "the current attempt's start, or the last enqueue" |
| M-8 prod key fail-fast | Not done; it goes to the orchestrator. Refusing to boot without a key is a deploy-wave call: it blocks a deploy, where the current behavior means overrides |
| M-9 action name | Now `retry_llm_check`, matching the plan and the operation id |
