# Review: workstream E (review workflow)

One fresh whole-branch reviewer, given the code rather than the author's conclusions. It reviewed HEAD `47412c9`
against spec §4.1–4.3 and §6, product-spec, decisions.md "Workflow policies", the ledger rulings, Foundation's
interfaces, and the plan's rulings.

The reviewer reproduced three of the four Critical/Important findings with a scratch probe test outside the
worktree. Each fix below landed with a test that fails on the pre-fix code and passes after; all six were run
RED against `HEAD~` before the fix commit. Resolutions are in `c4ddea1`.

## Findings and resolutions

1. **Critical: carry-forward re-applied a dismissal the reviewer later reversed.**
   - Sequence: v1 dismissed, then v2 (same text) accepted, then v3 (same text) came back dismissed, carried from
     v1, and a plain Approve passed.
   - The same hole existed in approve-with-edits.
   - **Fixed:** `_carryable_dismissals` takes the latest earlier occurrence of each `(rule_id, quote)` in any state,
     and carries only if every finding there is dismissed.
   - Test: `test_a_later_accept_beats_an_older_dismissal`.

2. **Critical: re-posting approve-with-edits approved a version with accepted findings.** The accepted-findings
   check ran only on plain Approve, and any current reviewer-edit version could be "approved with edits" with no
   new edits.
   - **Fixed:** every approval refuses accepted findings on the version being approved (the `plain` flag is gone;
     vN's accepted findings are exempt only because vN isn't the approved version).
   - **Fixed:** a re-post without text needs a reviewer-edit version with no decision yet.
   - Tests: `test_reposting_edits_refuses_findings_accepted_on_v2`,
     `test_an_already_decided_reviewer_version_needs_new_edits`.

3. **Important: reaffirm could never pass a failed AI check.** The gate demanded `llm_override_reason`, but
   `ReaffirmIn` had no such field.
   - **Fixed:** `ReaffirmIn.llm_override_reason` and the matching `reaffirm(..., llm_override_reason=)`, recorded
     on the decision.
   - Test: `test_reaffirm_after_a_failed_ai_check_takes_an_override`.

4. **Important: `reopen_item`/`send_back` invited a lock-order deadlock.** "Joins the caller's transaction",
   combined with the row-lock-then-advisory-lock order, deadlocks a multi-item fan-out against a concurrent claim.
   - **Resolved by contract:** both docstrings now state one item per transaction; the report's F block says the
     same. The sweep already ran one transaction per item.
   - **Not enforced in code.** A runtime guard can't tell a fan-out's outer transaction from pytest-django's
     test transaction, which wraps every service test.
   - The alternative, "advisory lock before any row lock" everywhere, still deadlocks against an F that locks a
     row first. Either way F must follow a contract.

5. **Important (judgment): spanless human checklist dismissals carried forever.** A Reg B imagery dismissal on
   v1 covered a changed creative on v5.
   - **Fixed, with a ruling:** human items carry only into `reviewer_edit` and `fast_track` versions, where only
     the text can have changed.
   - A marketer's resubmission starts the checklist open again.
   - Not carrying at all would have made every approve-with-edits two-phase, because the checklist always
     reappears on v+1.
   - Test: `test_human_checklist_dismissals_carry_only_into_text_only_versions`.

6. **Minor: gate order differed from the plan.**
   - **Fixed:** stale offer terms go first, since triage can't fix them. Then open, accepted, AI.
   - The module docstring and the report match.

7. **Minor: pull with explicit `placement_ids` didn't check liveness.**
   - **Fixed:** the ids are filtered through `live_placements_q`, and anything not live is refused on the field.
   - Test: `test_pull_refuses_ended_placements`.

8. **Minor: the reject path used `timezone.localdate(at)`, not the clock.**
   - **Fixed:** `_write` takes the clock.

9. **Minor: the warning pass wasn't isolated per item.**
   - **Fixed:** each warning catches `DomainError`, logs it and skips the item, like the expiry pass.

10. **Minor: partner attachment reads looked inconsistent.** Marketers get 200 on `GET /partners/{id}` with
    empty attachments but 403 on `/attachments`, and decision evidence rows show them a partner agreement's
    filename.
    - **Kept as is:**
      - The detail page serves marketers (partner pickers, context), so it stays 200 and drops what they can't
        read.
      - The list endpoint exists only to read the attachments, so it refuses.
      - Filenames in evidence rows are metadata the ruling doesn't restrict. Downloads are blocked.
    - Recorded in the report.

11. **Minor: stale docs.**
    - **Fixed:** plan ruling 6 now matches `47412c9` (current assignee first, then the last approver).
    - **Fixed:** `DecisionIn`'s description says to resend `llm_override_reason` on a re-post when the carried AI
      status is failed.

## Checked and found correct (reviewer)

- **Transitions:** the table matches the doc. `apply_transition` is the only status writer, every service calls
  it inside `atomic()`, and every action writes its event.
- **`reopen_reason`:** its lifecycle matches Foundation's queue-priority contract.
- **Lock order:** row before advisory in every single-item path. Pool and load are read after the lock.
- **Concurrency test:** the negative control is real, and it doesn't rely on a timeout.
- **Stale version:** checked before any write. A failed decision rolls back `start_review`.
- **Approve-with-edits two-phase:** leaves consistent committed state.
- **`open_findings_count`:** written by every action that changes findings or the current version.
- **Evidence:** limited to the item, its versions and its partner.
- **Dates:** expiry month math, send window and fallback are right; so are the retention rules.
- **Sweep:** idempotent, with per-item transactions.
- **Settings:** `secure_admin_login` behaves as intended with allauth 65.20.1 under `HEADLESS_ONLY`.
- **Library:** the scopes and precedent search match the ledger ruling.
