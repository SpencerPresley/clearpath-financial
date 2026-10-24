# Review: offer terms (workstream F, `wsF/offer-terms`)

Fresh whole-branch review against `origin/main`. Suite: `terms` 52 passed. The reproductions below come from
scratch tests that were run and then removed from the worktree (kept at
`/private/tmp/claude-501/-Users-spencer-code-promptarmor/51393cec-f963-4ef3-9f0b-5094c8f43a9e/scratchpad/test_zz_review_scratch{,2}.py`).

**No Critical findings.** The fan-out is correct under redelivery and concurrency: there are no double versions,
no double events, and no deadlocks. The row lock in `fan_out_item` serializes duplicate tasks. A second task
re-reads the item and its refs after the first commits and returns `skipped`. The per-item transaction keeps E's
lock order. The two concurrency tests prove what they claim, and the single-transaction control really
deadlocks. The selector picks the right rows: the latest approving decision, superseded terms, legacy excluded,
and needs_rereview limited to an approved or generated current version. It doesn't loop on the fast-track path,
because the generated version's refs link to the terms in effect.

## Important

### I1. The review screen's one-click Fast-track can approve a version the reviewer never saw. Verified.

- **Where:**
  - `backend/terms/fast_track.py:36-56`: `_current_n`, then `version_n=_current_n(item_id)`.
  - `backend/reviews/schemas.py:360`: `BulkFastTrackIn` has no versions.
  - `frontend/src/features/review/DecisionPanel.tsx:218-226`: the single button calls `useBulkFastTrackApprove`, then runs `settle(currentN)`.
- **Failure:**
  1. The reviewer opens an item at v2 (12.99%).
  2. A lead publishes v3 terms (9.99%), and the fan-out generates v3 copy.
  3. The reviewer clicks Fast-track.
  4. The bulk endpoint reads the current n (3) and approves v3. It records the reviewer as the approver of copy
     they never saw.
  5. The UI then settles on its stale `currentN` (2).
- **Why it matters:** `stale_version` exists for exactly this case, and the single endpoint enforces it. But the
  only UI path doesn't use the single endpoint.
- **Repro:** `test_bulk_approves_a_version_the_reviewer_never_saw` passes: `(seen_n, decision.version.n) == (2, 3)`
  and the approved text contains "9.99%".
- **Fix:**
  - Make bulk take `items: [{item_id, version_n}]`, so the queue's bulk carries the n each row showed.
  - Switch `DecisionPanel` to `fastTrackApprove` with `version_n`.
  - Drop `_current_n`.

### I2. `publish_terms` has no optimistic concurrency, so a second lead silently reverts the first. Verified (sequentially); the concurrent ordering is traced.

- **Where:** `backend/terms/services.py:55-59`. `now` is taken before `_lock`, and the input has no expected
  current version.
- **Failure, the lost update:**
  1. Leads A and B both load the form at v1.
  2. A publishes `apr_min` 12.99, which creates v2.
  3. B publishes a fee change with v1's `apr_min` of 7.49. B's publish succeeds as v3 and puts 7.49 back.
  4. Every item fans out twice, and the end state reverts A's rate. Neither lead is told.
  5. B's impact preview was computed against v1 and is now wrong too.
- **Repro:** `test_second_publish_silently_reverts_the_first` passes: v3's `apr_min == 7.49`.
- **Companion edge, from the concurrent ordering:** when the lead who loses the advisory lock captured `now`
  before the winner did, the closing check `lower >= now` fires. The loser gets `terms_range_overlap` with the
  message "publish after that". The report says this 409 happens "only on a clock anomaly", which is wrong.
- **Fix:**
  - Add `expected_current_terms_id: int | None` to `OfferTermsPublishIn` and `PublishTermsInput`. If it doesn't
    match `previous` under the lock, return 409 `conflict`, and have the frontend re-run the preview.
  - Take `now` after `_lock()`.

### I3. Normal-lane items stay on the work list forever, and the reconcile beat re-runs them every 15 minutes. Verified.

- **Where:**
  - `backend/terms/selectors.py:83,128-140`: `AFFECTED_STATUSES` includes needs_rereview, and an item counts when current == approved.
  - `backend/terms/tasks.py:42-53`
  - `backend/terms/fanout.py:71`: logs at INFO with `exc_info=True`.
- **Failure:**
  1. An approved, live item hits `StaleTermsRef` and becomes `needs_rereview` with no generated version.
     Current == approved, and the copy still quotes v1.
  2. `affected_approvals` keeps returning it. So every reconcile run enqueues it again, the task returns
     `regenerate_failed`, and it logs a full traceback.
  3. The `logger.warning("reconcile enqueued N items")` fires every 15 minutes forever. Each item that legitimately
     takes the normal lane holds it open until a human resolves the item. The beat's docstring says the task is
     "a no-op when the fan-out is healthy", and the warning was meant to be the signal that something was lost.
     It now fires all the time, so it signals nothing.
- **Related preview bug:** the impact preview counts the same items as "1 item already in re-review will get the
  new numbers" while their lane is `normal`. The repro printed exactly that summary with
  `[(normal, needs_rereview)]`.
- **Repro:** `test_normal_lane_item_stays_on_the_work_list_forever` passes, with three straight
  `REGENERATE_FAILED` results.
- **Checked and ruled out:** a refused reaffirm does not relink the approved version's refs to new terms. The
  `terms_ref_unique_span` key excludes `offer_terms`, and `ignore_conflicts` keeps the old rows. So the selector
  doesn't silently drop these items either (scratch 2).
- **Fix:**
  - Scope `reconcile_fan_out` to `status=APPROVED`, since the lost-enqueue window it covers is approved →
    sent back. Regenerating needs_rereview items stays a single attempt per publish, made by the handler.
  - Log `StaleTermsRef` without `exc_info` at INFO, or once at WARNING.
  - In `impact._summary`, count `already` only for lane `fast_track`, and list needs_rereview items in the normal
    lane separately.

## Minor

- **M1. A publish blocks every concurrent ref insert for its product for the whole transaction.** Traced, not run.
  `services.py:59`: `select_for_update()` takes FOR UPDATE on the open `OfferTerms` row. Every TermsRef insert
  (submit, resubmit, reviewer edit, fan-out task) takes FOR KEY SHARE on that row through its FK, and FOR UPDATE
  conflicts with it. So those inserts wait until publish commits, and the publish transaction includes
  `affected_approvals`, which loads every affected item's text (`services.py:87`). This is a stall, not a
  deadlock: publish waits on nothing item-side. A waiter that resumes links its refs to the now-closed version.
  Fixes:
  - Use `select_for_update(no_key=True)`; the per-product advisory lock already serializes publishers.
  - Compute `affected_item_ids` with an ids-only query.
- **M2. One failed enqueue drops the rest of the batch.** Verified against Django source. `handlers.py:28`:
  `transaction.on_commit` uses the default `robust=False`. In `run_and_clear_commit_hooks`
  (`django/db/backends/base/base.py:753-766`), a non-robust callback that raises propagates and the rest are
  dropped. One broker error on the first item's `.delay` leaves every remaining item for the reconcile, up to
  15 minutes later. Fix: `on_commit(..., robust=True)`, or a single callback that loops and logs.
- **M3. Items that a reviewer has claimed are skipped by later terms changes.** Traced. A re-review claimed into
  `in_review` isn't in `AFFECTED_STATUSES`, so a second publish doesn't regenerate its generated version. It
  isn't stuck: approve is refused with `stale_offer_terms`, while approve-with-edits and request-changes still
  work. But the fast-track lane is lost. The same applies to `expired(terms_changed)`, which the report already
  notes. This needs at least a line in the report's open risks.
- **M4. Bulk is a reviewer action, but product-spec Roles says bulk actions are Lead-only.** This is plan ruling 6.
  The per-item scoping makes it safe. Combined with I1, though, bulk is now the main one-click path, so fixing I1
  matters more than the role question.
- **M5. The publish payload's id list is unbounded.** `TermsPublishedPayload.affected_item_ids` holds every
  affected item in one event row. That's fine at the current scale. It's worth a count-plus-cap if the number of
  products or items grows.

## Test gaps

- **The normal-lane re-run loop (I3) has no test.** The scratch repro above can become the test.
- **No test for stale bulk input (I1) or for a stale publish base (I2).**
- **The `conflict` 409 has no test.** That's a needs_rereview item whose current version isn't generated, for
  example after `send_back(APPROVAL_EXPIRED)` with no terms change. The API docstring claims this 409, but no
  test exercises it.
- **`test_fan_out_is_idempotent_under_redelivery` is sequential.** The concurrent case relies on the
  `locked_item` row lock. I traced that it holds, but no test runs two tasks at once.
- **`test_reconcile_picks_up_items_a_lost_enqueue_left_behind` depends on wall-clock time.** It uses
  `SYSTEM_CLOCK` against data from `FixedClock` (2026-10-24 15:00 UTC), so it fails if run before then. The
  report acknowledges this. Passing `clock` into `reconcile_fan_out` as a parameter would remove the dependency.

## Report claims checked

- "409 terms_range_overlap only on a clock anomaly": **false** (I2).
- "Nothing else leaves an approval quoting superseded terms" / reconcile "no-op when healthy": **false** for
  needs_rereview items in the normal lane (I3).
- "The review screen (I) … works unchanged": it works, but it bypasses `version_n` (I1).
- "Four queries whatever the item count" and "flat query count" in the preview: consistent with the code and the
  passing test.
- "No edits to `reviews/` services": true. The only changes in `reviews/` are API stub removals.

## Resolutions (author)

| Finding | Resolution | Test |
|---|---|---|
| I1 | Fixed in the backend. `BulkFastTrackIn` (moved to `terms/schemas.py`) takes optional `seen_versions: [{item_id, version_n}]`; a listed item is approved only at that n, else skipped `stale_version`. Kept optional so the merged review screen's `{item_ids, reason}` call still works; the report asks I/J to send it, or switch to `fastTrackApprove` | `test_bulk_skips_an_item_whose_version_changed_since_it_was_seen` |
| I2 | Fixed. `based_on_terms_id` is required on publish (null for a first version); a mismatch under the lock is 409 `conflict`. `now` is read after the lock. Report corrected | `test_stale_base_is_refused_instead_of_reverting_another_leads_change`, `test_first_publish_must_say_there_was_no_base`, API test's `stale` case |
| I3 | Fixed. The reconcile covers approved items only (`affected_approvals(statuses=...)`); `StaleTermsRef` is logged at INFO without a traceback; the preview promises new numbers only to fast-track-lane re-reviews | `test_reconcile_leaves_normal_lane_rereviews_alone`, `test_normal_lane_rereviews_are_not_promised_new_numbers` |
| M1 | Fixed. The row lock is gone; the per-product advisory lock already serializes publishers. `affected_item_ids` still loads the copy (it's the same selector), within one publish | — |
| M2 | Fixed: `on_commit(..., robust=True)` | — |
| M3 | Documented in the report's open risks | — |
| M4 | Kept (plan ruling 6); listed as a decision for Spencer | — |
| M5 | Documented in the report's open risks | — |
| Test gaps | `conflict` 409: `test_only_a_generated_version_can_be_fast_tracked`. Reconcile takes a `clock`, so its test no longer depends on wall-clock time. The concurrent duplicate-task case is still covered only by the row-lock trace | — |
