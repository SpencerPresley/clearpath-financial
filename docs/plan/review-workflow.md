# Review workflow (workstream E) Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans), then one fresh whole-branch
> reviewer. **Why not subagent-driven:** every task writes through the same transition function, the same
> `open_findings_count` writer, the same gate list, `reviews/api.py`, `reviews/schemas.py` and the
> `test_contract.py` stub list. Parallel implementers would collide on those files, and sequential ones would
> each re-read ~3k lines of Foundation to learn one shared vocabulary. The independent read comes from the
> whole-branch review (`docs/plan/reviews/review-workflow.md`).

**Goal:** Replace every Foundation stub assigned to E: code checks wired into persistence, auto/manual
assignment under an advisory lock, the item state machine, findings triage, decisions with gates, placements,
the daily expiry sweep, attachment read permissions, the library selector, and the #18 security follow-ups.

**Architecture:** One typed transition table (`reviews/transitions.py`) is the only code that changes
`ReviewItem.status`; every action calls `apply_transition`, which checks the from-status, sets the status,
applies the `reopen_reason` rule, and records the event in the caller's transaction. Actions are grouped by
family into sibling modules of `reviews/services.py` (assignment, versions, decisions, rereview, placements);
`checks/services.py` is the only writer of `Finding`/`TermsRef`/`CheckRun` and of `open_findings_count`.

**Tech stack:** Django 6.1 + ninja 1.7, Postgres 17 (advisory locks), Celery beat, pytest on real Postgres.

**Spec:** `docs/spec.md` §4.1–4.3, §6; `docs/product-spec.md` (status machine, automation);
`docs/decisions.md` "Workflow policies"; `docs/plan/ledger.md` "Rulings"; `docs/plan/reports/foundation.md`
(Interfaces, Conventions); `docs/plan/reports/rules-engine.md`.

## Global constraints

- Every status change: `apply_transition` inside `transaction.atomic()`, one Event with `from_status`/`to_status`.
- Domain failures are typed exceptions (`core.errors` or `reviews.errors`), mapped once by `config.api`; no
  try/except in endpoints. Expected outcomes (bulk skips) are values.
- Time is injected (`clock: Clock = SYSTEM_CLOCK`) everywhere: services, sweep, expiry, liveness.
- Lock order in any transaction that assigns: item row lock (`select_for_update`) first, then
  `pg_advisory_xact_lock(ASSIGNMENT_LOCK_KEY)`; never lock a second item after the advisory lock.
- List endpoints return lists; `{int:id}` path params; `Status(201, body)`; no raw dicts; no `choices=`.
- Implemented stubs leave `config/tests/test_contract.py::STUBS` and switch `STUB_ERRORS` → `ERRORS`;
  `make schema` after any schema change.
- Env: `CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=clearpath-dev POSTGRES_PORT=55432
  REDIS_URL=redis://localhost:56379/0 CLEARPATH_TEST_DB_SUFFIX=wsE`.

## Transition table (`reviews.transitions.TRANSITIONS`)

| Action | From | To | Event | `reopen_reason` |
|---|---|---|---|---|
| `submit` | (new) | submitted | ITEM_SUBMITTED | — (Foundation's `submit_item`) |
| `start_review` | submitted, needs_rereview | in_review | ITEM_REVIEW_STARTED | kept |
| `approve` | in_review | approved | DECISION_RECORDED | cleared |
| `request_changes` | in_review | changes_requested | DECISION_RECORDED | kept |
| `reject` | in_review | rejected | DECISION_RECORDED | cleared |
| `fast_track_approve` | needs_rereview | approved | DECISION_RECORDED (lane fast_track) | cleared |
| `reaffirm` | needs_rereview | approved | DECISION_RECORDED (lane reaffirm) | cleared |
| `resubmit` | changes_requested | submitted | ITEM_RESUBMITTED | kept |
| `reopen` | approved | needs_rereview | ITEM_REOPENED | set |
| `expire` | approved | expired | ITEM_EXPIRED | set |
| `pull` | needs_rereview | withdrawn | ITEM_WITHDRAWN | cleared |
| `new_round` | withdrawn, expired | submitted | ITEM_NEW_ROUND_STARTED | cleared |

`draft` is in the enum but nothing enters it: resubmit and new round go straight to `submitted` (intake has
no drafts). A decision or triage by the assignee on a `submitted` item first applies `start_review`, so
ITEM_REVIEW_STARTED is the one "first review" marker metrics key on. `needs_rereview → in_review` happens only
through `claim` (an explicit full review); triage on a fast-track version leaves the item in needs_rereview.

## Rulings made here (reversible; recorded again in the report)

1. **Approve needs every finding on the approved version dismissed** (open blocks per ruling 3; *accepted*
   also blocks, because accepted = required change and the approved version is exactly what goes live).
   Approve-with-edits needs vN triaged (accepted is fine: the edits address them) and v+1 clean.
2. **Approve-with-edits is two-phase when v+1 raises findings.** v+1 (`reviewer_edit`) is persisted with its
   code findings and carried dismissals. If any v+1 finding is open, the service commits v+1 and raises
   `FindingsNeedTriage` (409, findings in `details`); the reviewer triages and re-posts `approved_with_edits`
   on `version_n = v+1` without text (only while v+1 is undecided). Otherwise the approval is recorded in the
   same call.
2a. **Human checklist dismissals carry only into reviewer-edit and fast-track versions** (added after review):
   a marketer's resubmission may carry a new creative, so its checklist starts open.
3. **AI check on reviewer-edit versions is carried, not re-run** (deviation from ruling 4): v+1 keeps vN's
   `llm_check_status` and the decision records `ai_review_carried_from = vN`. D2's handler skips
   `origin=reviewer_edit`. Fast-track versions set `llm_check_status = skipped` (ruling 4).
4. **Approvals refuse superseded offer terms** (`StaleOfferTerms`, 409): if the version's TermsRefs point at
   a terms version not in effect now, approve/reaffirm/fast-track are refused. Otherwise F's fan-out (which
   looks for items quoting the *old* version) would miss an approval recorded against an already-old version.
5. **Reaffirm re-runs code checks** on the same version (insert-only, existing rows win the unique key); any
   new open finding is committed and the reaffirm refused (409 `findings_need_triage`).
6. **Sticky assignment respects availability**: the previous reviewer (the current assignee, so a lead's manual
   reassignment holds; else the approver of the latest decision) gets it back only if active, available, a
   reviewer by effective role, and not the owner; otherwise lowest load. Leads who reviewed get sticky work back (effective role); the lowest-load pool
   uses stored `reviewer` (Foundation).
7. **Decider and triager = the assignee or a lead**; never the item's owner (no self-review).
8. **Expiry**: `fixed_months` → decided_at + N months (day clamped to month end); `send_window` → midnight
   after `max(planned_last_run or planned_first_run, today)`; channel missing from `ExpiryPolicy` → 6 months.
9. **Retention**: `retention_until = max(last_run) + 24 months` (Reg N 1014.5), 36 months for prescreen items
   (FCRA 1681m(d)(3)); `None` while any placement is open-ended without a confirmed takedown. Recomputed by the
   placement actions, not the sweep.
10. **Code-check `CheckRun` is recorded, never looked up** by content hash: the context (channel, markets,
    attachments, terms) isn't in the cache key. `ruleset_key = f"{RULESET_VERSION}/{ENGINE_VERSION}"`.
11. **30-day expiry warning** is an event (`item.approval_expiring`, one per approval decision) with a
    notification handler to owner + assignee.

## Interfaces (for F, G, D2, I)

```python
# reviews.transitions
class Action(StrEnum): START_REVIEW, APPROVE, REQUEST_CHANGES, REJECT, FAST_TRACK_APPROVE, REAFFIRM,
                       RESUBMIT, REOPEN, EXPIRE, PULL, NEW_ROUND
TRANSITIONS: Mapping[Action, Transition(sources: frozenset[ItemStatus], target: ItemStatus, event: EventType,
                                        reopen: Literal["keep", "set", "clear"])]
apply_transition(item: ReviewItem, action: Action, *, actor: User | None, at: datetime, payload: EventPayload,
                 entity: EntityType = ITEM, entity_id: int | None = None,
                 reopen_reason: ReopenReason | None = None) -> Event   # InvalidTransition otherwise; saves item

# reviews.assignment
ASSIGNMENT_LOCK_KEY: int
auto_assign(*, item: ReviewItem, actor: User | None, clock: Clock, sticky: bool) -> Assignment
  Assignment(assignee_id: int | None, mode: AssignmentMode, reason: str)       # writes ITEM_ASSIGNED
claim_item(*, actor, item_id, clock) -> None
assign_item(*, actor, item_id, assignee_id: int | None, reason: str, clock) -> None   # lead: manual; own: handoff
bulk_assign(*, actor, item_ids, assignee_id, reason, clock) -> BulkResult
BulkResult(succeeded: tuple[int, ...], skipped: tuple[BulkSkip(item_id, code, message), ...])
run_bulk(item_ids, action: Callable[[int], object]) -> BulkResult   # F's bulk fast-track reuses this

# reviews.versions
create_version(*, item, text, author, origin: VersionOrigin, clock, based_on: Version | None = None)
  -> CreatedVersion(version: Version, checks: PersistedChecks)   # runs code checks, sets current_version and
  # open_findings_count; origin fast_track -> llm skipped, reviewer_edit -> carried; records VERSION_CREATED
  # only for reviewer_edit / fast_track (submission versions ride on their action's event)
resubmit_item(*, actor, item_id, content_text, note="", clock) -> VersionResult
start_new_round(*, actor, item_id, content_text: str | None, clock) -> VersionResult
VersionResult(item_id, version_id, version_n, round, event_id)

# reviews.decisions
DecisionInput(outcome, version_n, reason, evidence_attachment_ids=(), llm_override_reason=None,
              edited_content_text=None, lane=DecisionLane.STANDARD)
record_decision(*, actor, item_id, data: DecisionInput, clock) -> DecisionResult(decision_id, version_n, status)
  # F: lane=FAST_TRACK on a needs_rereview item whose current version is origin fast_track
reaffirm(*, actor, item_id, reason, clock) -> DecisionResult
pull_item(*, actor, item_id, reason, placement_ids: tuple[int, ...] = (), clock) -> None
approval_expiry(*, channel: Channel, decided_at, planned_first_run, planned_last_run, today) -> datetime

# reviews.rereview — the only approved -> * writers besides decisions
reopen_item(*, item_id, reason: ReopenReason, clock, actor=None, offer_terms_id=None,
            generated_version_id=None) -> int  # event id; approved -> needs_rereview, sticky re-assignment
expire_item(*, item_id, reason: ReopenReason, clock, actor=None, offer_terms_id=None,
            generated_version_id=None) -> int  # approved -> expired
send_back(*, item_id, reason, clock, ...) -> int   # live ? reopen_item : expire_item  (F's fan-out entry)
run_expiry_sweep(*, clock) -> SweepResult(reopened, expired, warned, skipped)   # Celery: reviews.expiry_sweep

# reviews.placements
record_placement(*, actor, item_id, data: PlacementInput, clock) -> int
update_placement(*, actor, placement_id, changes: PlacementChanges, clock) -> None
confirm_takedown(*, actor, placement_id, clock) -> None
# reviews.selectors
is_item_live(*, item_id, today) -> bool
library_items(*, viewer, filters, scope: LibraryScope = APPROVED_TO_RUN | EVER_APPROVED, sort, cursor, limit, clock) -> ItemPage

# checks.services — the only writer of Finding/TermsRef/CheckRun and of item.open_findings_count
run_code_checks(*, version, clock) -> PersistedChecks(result, open_findings_count)
persist_findings(*, version, drafts: Sequence[FindingDraft], clock) -> int   # carries dismissals; D2 uses it
recount_open_findings(*, item_id) -> int      # writes the column; D2 calls it after persisting LLM findings
rule_context(*, version, clock) -> RuleContext
preview_checks(*, data: PreviewInput, clock) -> PreviewResult   # stateless, for POST /checks/preview
accept_finding / dismiss_finding / reopen_finding(*, actor, finding_id, note|reason, clock) -> None
```

- **D2:** run the AI check on ITEM_SUBMITTED, ITEM_RESUBMITTED, ITEM_NEW_ROUND_STARTED (all carry
  `version_id`); skip VERSION_CREATED (`reviewer_edit` carries, `fast_track` skips). Persist through
  `persist_findings`, then `recount_open_findings`; set `llm_check_status` only if the version is still current.
- **I (frontend):** 409 codes: `invalid_transition`, `open_findings_block_decision`,
  `accepted_findings_block_approval`, `findings_need_triage` (details: `version_n`, `findings`),
  `stale_version`, `stale_offer_terms`, `ai_check_pending`; 422 field `llm_override_reason`. The SPA needs a
  `/login?next=` route: Django admin login redirects there (`LOGIN_URL`).

## Review focus

- Two concurrent submits must not pick the same reviewer from a stale load → `test_concurrent_assignment_*`.
- A decision posted against v1 after the marketer resubmitted v2 → `stale_version`, nothing written.
- Approve-with-edits whose text re-triggers a dismissed finding with an identical quote → carried, approval
  goes through; a new quote → 409 with v+1 kept.
- The sweep run twice on the same day writes nothing the second time (idempotent reopen/expire/warn).
- Pull with `placement_ids` of another item, or an already-confirmed takedown → InvalidInput, nothing written.

## Tasks

Each task: failing test first, then code, then the task's tests + ruff + pyrefly, then commit.

1. **Checks wiring** (`checks/services.py`, `checks/tests/test_services.py`): `rule_context`,
   `run_code_checks` (findings incl. `human_checklist`, TermsRefs to the current OfferTerms row, CheckRun,
   CHECKS_COMPLETED), `persist_findings` with carry-forward (latest dismissed finding with the same
   `(rule_id, quote)` on an earlier version of the item; FINDING_DISMISSED `carried=True`, actor None), dedupe
   on `(source, rule_id, span)`, `recount_open_findings`, `preview_checks` + `POST /checks/preview`.
   Tests: submit persists findings and count; human items have no span; TermsRef points at the current row;
   carry-forward; preview persists nothing and returns refs; MTG has no refs.
2. **Transitions** (`reviews/transitions.py`, `reviews/errors.py`): table, `apply_transition`. Tests: table
   matches the doc table; every non-source status raises `InvalidTransition`; reopen-reason rule; event
   from/to.
3. **Assignment** (`reviews/assignment.py`, wire into `submit_item`): lock, eligible pool, weighted load,
   tie-break `last_assigned_at` nulls first then id, sticky, pool + lead notification, claim, manual, handoff,
   bulk. Concurrency test with `transaction=True`, two threads, a pause hook after the lock, and a negative
   control without the lock.
4. **Versions** (`reviews/versions.py`): `create_version`, `resubmit_item`, `start_new_round`; round bump,
   sticky assignment, `llm_check_status`, `ItemResubmittedPayload.note`.
5. **Triage** (`checks/services.py`): accept/dismiss/reopen with permissions, current-version and status
   guards, auto `start_review`, recount. API endpoints.
6. **Decisions** (`reviews/decisions.py`): gates in order (status → permission → stale version → stale terms
   → open → accepted (approve) → AI), approve-with-edits two-phase, evidence (item, its versions, the item's
   partner), expiry, `engine_version` column + migration, reaffirm, pull. API endpoints.
7. **Placements + rereview + sweep** (`reviews/placements.py`, `reviews/rereview.py`, `reviews/tasks.py`):
   record/update/confirm-takedown, retention, reopen/expire/send_back, sweep + 30-day warning event, beat entry.
8. **Reads**: attachment read permission (partner attachments: reviewer/lead/admin), library scope and
   precedent search restricted to ever-approved versions.
9. **#18**: `CACHES` → Django `RedisCache` (locmem in tests), `secure_admin_login` + `LOGIN_URL`, IMDS note.
10. **Contract**: `make schema`, stub list, query-count cases for new reads, report, review, PR.
