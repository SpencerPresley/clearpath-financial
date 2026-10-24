# Review workflow (workstream E): report

Branch `wsE/review-workflow`, closes #6 and #18. Plan: `docs/plan/review-workflow.md`. Review with resolutions:
`docs/plan/reviews/review-workflow.md`.

Executed natively, not subagent-driven. Every task writes through the same transition function, the same
`open_findings_count` writer, the same gate list, `reviews/api.py`, `reviews/schemas.py` and the
`test_contract.py` stub list. Parallel implementers would have collided on those files, and sequential ones would
each have re-read about 3k lines of Foundation to learn one vocabulary. The independent read came from one fresh
reviewer over the whole branch.

## What shipped

| Area | Where | Notes |
|---|---|---|
| Code checks wired | `checks/services.py` | Engine + human checklist persisted; TermsRefs to the OfferTerms row in effect; one `CheckRun` per run (`ruleset_key = RULESET_VERSION/ENGINE_VERSION`); CHECKS_COMPLETED; dismissals carried for identical `(rule_id, quote)`; `POST /checks/preview` stateless |
| Transition table | `reviews/transitions.py` | One typed table; `apply_transition` is the only writer of `status` |
| Assignment | `reviews/assignment.py` | Sticky, lowest weighted load, pool; `pg_advisory_xact_lock`; claim, manual, hand-off, bulk |
| Versions | `reviews/versions.py` | Resubmit, new round (from withdrawn/expired), `create_version` for reviewer edits and F's fast-track |
| Triage | `checks/services.py` | Accept, dismiss (reason), reopen; current version only; assignee or lead |
| Decisions | `reviews/decisions.py` | Gates, two-phase approve-with-edits, evidence, expiry, reaffirm (re-checks), pull, reject takes live content down |
| Placements | `reviews/placements.py` | Record, update, confirm takedown, retention dates |
| Re-review / expiry | `reviews/rereview.py`, `reviews/tasks.py` | `send_back` (live → needs_rereview, else expired); daily beat sweep; 30-day warning event |
| Reads | `reviews/records.py`, `reviews/selectors.py`, `reviews/search.py`, `partners/*` | Partner attachments: reviewers/leads/admins only; library scopes; precedent search on ever-approved versions |
| #18 | `config/settings/base.py`, `config/urls.py`, `docs/decisions.md` | `CACHES` on Django's `RedisCache`; admin login via allauth `secure_admin_login`; IMDS hop-limit note |

Migration: `reviews.0007_decision_engine_version` (adds `Decision.engine_version`, default `""`; the insert-only
trigger isn't involved in `ALTER TABLE`).

## Transition table

| Action | From | To | Event | `reopen_reason` |
|---|---|---|---|---|
| `submit` | (new) | submitted | ITEM_SUBMITTED | — |
| `start_review` | submitted, needs_rereview | in_review | ITEM_REVIEW_STARTED | kept |
| `approve` | in_review | approved | DECISION_RECORDED | cleared |
| `request_changes` | in_review | changes_requested | DECISION_RECORDED | kept |
| `reject` | in_review | rejected | DECISION_RECORDED | cleared |
| `fast_track_approve` | needs_rereview | approved | DECISION_RECORDED (lane fast_track) | cleared |
| `reaffirm` | needs_rereview | approved | DECISION_RECORDED (lane reaffirm) | cleared |
| `resubmit` | changes_requested | submitted | ITEM_RESUBMITTED | kept |
| `reopen` | approved | needs_rereview | ITEM_REOPENED | set |
| `expire` | approved | expired | ITEM_EXPIRED | set |
| `pull` | needs_rereview | withdrawn | ITEM_WITHDRAWN (+ TAKEDOWN_REQUESTED each) | cleared |
| `new_round` | withdrawn, expired | submitted | ITEM_NEW_ROUND_STARTED | cleared |

- `draft` is never entered: intake has no drafts, and resubmit and new round go straight to `submitted`.
- A decision or triage by the assignee on a `submitted` item applies `start_review` first, so
  ITEM_REVIEW_STARTED is the single "first review" marker. Metrics (J) should key on it.
- `needs_rereview → in_review` happens only through `claim`. Triage on a fast-track version leaves the item in
  needs_rereview.
- `test_table_is_the_documented_machine` pins the table to the doc. A parametrized test runs every
  (action, status not in sources) pair and expects `InvalidTransition` with nothing written: 91 cases.

## Gate rules (record_decision, reaffirm, F's fast-track lane)

These are checked on the version being approved, in this order:

1. The decided version is the current one (`stale_version`).
2. The copy quotes no superseded offer terms (`stale_offer_terms`). This comes first because triage can't fix it.
3. No open finding, warnings and human checklist items included (`open_findings_block_decision`).
4. No *accepted* finding on the version being approved (`accepted_findings_block_approval`). Accepted means a
   required change, and the approved version is exactly what goes live. For approve-with-edits this is v+1,
   where vN's accepted findings were addressed.
5. AI check: `pending`/`running` → `ai_check_pending`. `failed` → `llm_override_reason` is required (422 on that
   field) and recorded; reaffirm takes it too. `succeeded`/`skipped` → pass.

Request changes and Reject need a non-blank reason only. Reject also requests takedown of any live placements.

**Approve with edits** first requires vN fully triaged (accepted is fine) and its AI check done. The reviewer's
text then becomes v+1 (`reviewer_edit`): code checks run and identical dismissals carry. If v+1 has open
findings, v+1 is committed as current and `findings_need_triage` (409, `details.findings`) returns them. The
reviewer triages and re-posts `approved_with_edits` on v+1 without text. That re-post works only while v+1 has
no decision. Otherwise v+1 is approved in the same call.

**Carry-forward** handles a finding with the same `(rule_id, quote)` as on an earlier version. It's created
dismissed only if the latest earlier version that raised it left it dismissed, so a later accept or reopen wins.
Human checklist items (no quote) carry only into reviewer-edit and fast-track versions; a marketer's
resubmission starts the checklist open.

**Reaffirm** re-runs the code checks on the same version first. New findings are committed and the reaffirm is
refused with `findings_need_triage`. After that, gates 2–5 apply.

**Every decision records:** the version, outcome, lane, approver, reason, `ruleset_date = RULESET_VERSION`,
`engine_version = ENGINE_VERSION`, the offer-terms versions quoted (from the version's TermsRefs), and evidence
with a sha256 snapshot (attachments on the item, its versions, or its partner). An approval also records
`expires_at` (ExpiryPolicy), `ai_review_carried_from` (based_on, for reviewer-edit and fast-track versions) and
the override reason.

## Interfaces for F, G, D2, I

```python
# reviews.transitions
Action, TRANSITIONS, require_transition(item, action) -> Transition
apply_transition(item, action, *, actor, at, payload, entity=ITEM, entity_id=None, reopen_reason=None) -> Event
start_review(item, *, reviewer, at) -> Event

# reviews.assignment  (item row lock first, then the advisory lock; never lock another item after it)
locked_item(item_id) -> ReviewItem                       # select_for_update; NotFound
auto_assign(*, item, actor, clock, sticky=False) -> Assignment(assignee_id, mode, reason)   # writes ITEM_ASSIGNED
require_reviewer_of(actor, item) -> None                 # assignee or lead, never the owner
claim_item / assign_item(*, actor, item_id, assignee_id, reason="", clock) / bulk_assign(...) -> BulkResult
run_bulk(item_ids, action: Callable[[int], object]) -> BulkResult(succeeded, skipped: BulkSkip(item_id, code, message))

# reviews.versions   (F: generate the fast-track version here, inside your transaction, item locked)
create_version(*, item, text, author, origin, clock, based_on=None) -> CreatedVersion(version, checks)
  # sets current_version; origin fast_track -> llm_check_status skipped; reviewer_edit -> carried;
  # writes open_findings_count; VERSION_CREATED for non-submission origins
resubmit_item(*, actor, item_id, content_text, note="", clock) -> VersionResult
start_new_round(*, actor, item_id, content_text=None, clock) -> VersionResult

# reviews.decisions
record_decision(*, actor, item_id, data: DecisionInput, clock) -> DecisionResult(decision_id, version_n, status)
  DecisionInput(outcome, version_n, reason, evidence_attachment_ids=(), llm_override_reason=None,
                edited_content_text=None, lane=DecisionLane.STANDARD)
  # F bulk fast-track: run_bulk(ids, lambda i: record_decision(actor=..., item_id=i, data=DecisionInput(
  #   outcome=APPROVED, version_n=<current n>, reason=..., lane=DecisionLane.FAST_TRACK), clock=...))
  # Items with open findings come back as skips with code open_findings_block_decision (ruling 4).
reaffirm(*, actor, item_id, reason, llm_override_reason=None, clock) -> DecisionResult
pull_item(*, actor, item_id, reason, placement_ids=(), clock) -> None
approval_expiry(*, channel, decided_at, planned_first_run, planned_last_run, today) -> datetime

# reviews.rereview   (F's fan-out entry point is send_back; legacy items raise Conflict)
send_back(*, item_id, reason, clock, actor=None, offer_terms_id=None, generated_version_id=None) -> int
reopen_item(...) -> int; expire_item(...) -> int     # same kwargs; the only automatic approved -> * writers
run_expiry_sweep(*, clock) -> SweepResult(reopened, expired, warned, skipped)

# reviews.placements
record_placement(*, actor, item_id, data: PlacementInput, clock) -> int
update_placement(*, actor, placement_id, changes: PlacementChanges("keep" | value), clock) -> None
confirm_takedown(*, actor, placement_id, clock) -> None

# reviews.selectors / records (G export, K tools)
is_item_live(*, item_id, today) -> bool
library_items(*, viewer, filters, scope: LibraryScope, sort, cursor, limit, clock) -> ItemPage
records.get_decision(*, decision_id) / get_placement(*, placement_id, clock)
records.can_read_partner_attachments(viewer) -> bool; get_attachment(*, attachment_id, viewer)
records.list_partner_attachments(*, partner_id, viewer)   # NotPermitted for marketers

# checks.services   (the only writer of Finding/TermsRef/CheckRun and of item.open_findings_count)
run_code_checks(*, version, clock) -> PersistedChecks(result, open_findings_count)
persist_findings(*, version, drafts, clock) -> int      # carries dismissals; dedupes on (source, rule_id, span)
recount_open_findings(*, item_id) -> int                # writes the column for the current version
rule_context(*, version, clock) -> RuleContext
preview_checks(*, data: PreviewInput, clock) -> PreviewResult
accept_finding / dismiss_finding / reopen_finding(*, actor, finding_id, note|reason, clock) -> None
```

- **F (offer terms):**
  1. Lock the item.
  2. `create_version(origin=FAST_TRACK, based_on=<approved version>, author=<lead>)`.
  3. `send_back(reason=TERMS_CHANGED, offer_terms_id=..., generated_version_id=...)`.
  4. Bulk approve through `run_bulk` + `record_decision(lane=FAST_TRACK)`, one item per transaction. `run_bulk`
     does that already; call `send_back` the same way, never several items in one transaction (lock order).
  5. Catch `StaleTermsRef` from `render_fast_track` and leave that item in the normal lane: `send_back` without
     a generated version.
  6. Find affected approvals by the approving Decision's `terms_versions` (or the approved version's TermsRefs).
- **G (export/evidence pack):** the decision record carries `engine_version`, `ruleset_date`, terms versions and
  evidence hashes (`records.get_decision`). Legacy items: `send_back` refuses them; the library's
  `ever_approved` scope includes legacy items imported as approved.
- **D2 (LLM):**
  - Register on ITEM_SUBMITTED, ITEM_RESUBMITTED and ITEM_NEW_ROUND_STARTED. All three carry `version_id`.
  - Skip VERSION_CREATED: reviewer edits carry vN's AI result (ruling 3), and fast-track skips the check.
  - Persist through `persist_findings`, then `recount_open_findings`.
  - Set `llm_check_status` only if `version_id` is still the item's current version.
  - Until D2 lands, `llm_check_status` stays `pending`, so **Approve is blocked on every real item** (see risks).
- **I (frontend):**
  - 409 codes: `invalid_transition`, `stale_version`, `open_findings_block_decision`,
    `accepted_findings_block_approval`, `ai_check_pending`, `stale_offer_terms`, `findings_need_triage`
    (`details.version_n`, `details.findings[{id, rule_id, severity, source, message, quote}]`),
    `invalid_finding_transition`.
  - 422 field errors: `llm_override_reason`, `reason`, `edited_content_text`, `evidence_attachment_ids`,
    `assignee_id`, `placement_ids`, `last_run`, `url`.
  - `PATCH /placements/{id}`: an omitted field is kept; `last_run: null` means open-ended.
  - `GET /library?scope=approved_to_run|ever_approved`.
  - The SPA needs a `/login?next=` route: Django admin login redirects there.

## Rulings made here (reversible)

- Ruling: every approval refuses accepted findings on the approved version — accepted = required change, and the
  approved version is what goes live — cost if wrong: drop gate 4.
- Ruling: human checklist dismissals carry only into reviewer-edit and fast-track versions — they have no quote,
  so carrying on `(rule_id, None)` would cover a changed creative forever; not carrying at all would make every
  approve-with-edits two-phase — cost if wrong: one origin set.
- Ruling: approve-with-edits is two-phase when v+1 raises findings (v+1 kept, 409 with them) — the brief's
  single call can't satisfy ruling 3's "every finding triaged" for findings that didn't exist before the call —
  cost if wrong: one endpoint contract.
- Ruling: reviewer-edit versions carry vN's AI result instead of re-running (deviation from ruling 4) — with the
  AI gate on, a fresh pending check on v+1 would make approve-with-edits impossible in one call; the decision
  records `ai_review_carried_from` — cost if wrong: D2 also runs on VERSION_CREATED(reviewer_edit), and the
  gate then applies to v+1.
- Ruling: approvals refuse superseded offer terms — F's fan-out finds approvals by the terms version they quote,
  so an approval recorded against an already-superseded version would never be fanned out again — cost if
  wrong: one gate.
- Ruling: reaffirm re-runs code checks and refuses on new findings — expiry exists to catch rule changes — cost
  if wrong: one call.
- Ruling: sticky goes to the current assignee, else the last decision's approver. The reviewer must be active,
  available, a reviewer by effective role (leads count) and not the owner; otherwise lowest load, and the reason
  says so — a lead's manual reassignment while the item sat with the marketer must hold ("manual assignment
  skips automatic") — cost if wrong: a condition.
- Ruling: `send_back`/`reopen_item` run one item per transaction (documented, not enforced) — they take the
  assignment lock after the item's row lock, so a multi-item transaction can deadlock against a concurrent claim.
  A runtime guard can't tell F's outer transaction from pytest's test transaction — cost if wrong: F must loop
  with a transaction per item.
- Ruling: deciders and triagers are the assignee or a lead, never the item's owner — cost if wrong: one check.
- Ruling: `send_window` expiry is midnight after `max(planned_last_run or planned_first_run, today)`; a channel
  missing from ExpiryPolicy gets 6 months — cost if wrong: a constant.
- Ruling: retention = last run + 24 months (Reg N 1014.5), 36 for prescreen (FCRA); `None` while any placement
  is open-ended; recomputed by placement actions, not the sweep — cost if wrong: a constant.
- Ruling: Reject requests takedown of live placements — rejecting re-reviewed content that is still running
  must stop it — cost if wrong: a few lines.
- Ruling: the 30-day expiry warning is an event (`item.approval_expiring`, once per approving decision),
  notified to owner and assignee — cost if wrong: one handler.
- Ruling: library `ever_approved` includes legacy items whose status is approved; precedent search covers only
  versions with an approving decision — cost if wrong: a filter.

## Deviations and shared-file touches

- **Module layout:** review actions are split by family into sibling modules (`transitions`, `assignment`,
  `versions`, `decisions`, `rereview`, `placements`) instead of growing `reviews/services.py` (already 400
  lines). Each module is a services module in the CLAUDE.md sense: the only writers, one function per action.
- **`submit_item` event order:** ITEM_SUBMITTED, then CHECKS_COMPLETED, then ITEM_ASSIGNED. Code checks moved
  after the event, so history reads in causal order.
- **Shared files, additive only:**
  - `core/domain.py`: `EventType.APPROVAL_EXPIRING`, `NotificationKind.EXPIRY_WARNING`.
  - `audit/payloads.py`:
    - `ApprovalExpiringPayload`.
    - `ItemResubmittedPayload.note`.
    - `DecisionRecordedPayload.ruleset_date`, `.engine_version`, `.ai_review_carried_from_version_id` and
      `.llm_override_reason`, all defaulted.
  - `notifications/handlers.py`: `notifications.expiry_warning`.
  - `partners/selectors.py` and `partners/api.py`: viewer-aware attachments, per the ledger ruling.
  - `config/tests/test_contract.py`: E's stubs removed. `test_stub_still_validates_input_first` now uses the
    fast-track stub.
  - `config/tests/test_query_counts.py`: one new case.
  - `docs/decisions.md`: the IMDS note (#18).
- **Redis client:** `redis` comes in through `celery[redis]`, so `pyproject.toml` is unchanged. That avoids a
  `uv.lock` conflict with D's branch. Tests use LocMem because CI has no Redis.
- **Not built:**
  - A marketer withdrawing a pending submission: it's not in the status machine.
  - Re-running checks when evidence is uploaded after submit: see risks.

## Verification

Filled in after the review fix pass (below).

## Open risks

- **Approve is blocked until D2 lands.** `llm_check_status` is `pending` on every new version and nothing moves
  it yet. That's spec-correct (ruling 3), but the running app can't approve anything until D2's handler merges.
  If D2 slips, a stopgap is to set `skipped` at submit when no `ANTHROPIC_API_KEY` is configured. That's D's
  call.
- **Evidence uploaded after submit doesn't re-run checks.** Intake creates the item first, then uploads. So
  `sms.consent_record`, `prescreen.criteria_on_file` and `claims.*` substantiation findings stay open until a
  reviewer dismisses them, citing the attachment. A recheck-on-upload would delete open code findings that no
  longer fire, which is a design change. Left for a ruling.
- **Cache and broker share a Redis DB** (keys prefixed `clearpath:`). With an `allkeys-*` eviction policy, broker
  keys could be evicted. Compose and the server run Redis without `maxmemory`.
- **#18 comment items not done:**
  - `ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "CloudFront-Viewer-Address"`: the value is `ip:port`, and the parse
    needs checking against real CloudFront traffic.
  - `DOCUMENTS_BUCKET`: S3 storage, owned by A/G.
  - The issue body's three items are done, and this PR closes #18. The two comment items need re-filing if
    still wanted.
