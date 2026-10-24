# Offer terms (workstream F) Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans), then one fresh whole-branch reviewer
> (`docs/plan/reviews/offer-terms.md`). **Why not subagent-driven:** five small tasks that all lean on one
> selector (`affected_approvals`) and one per-item service (`fan_out_item`), and on E's lock-order and gate
> contracts. Parallel implementers would each have to re-learn E's `reviews/*` vocabulary to write 50 lines.

**Goal:** A lead publishes a new OfferTerms version; every approved item quoting the old version gets a generated
v+1 with recomputed numbers and goes to `needs_rereview(terms_changed)` (live) or `expired(terms_changed)` (not
live); reviewers clear the live ones with one-click (or bulk) fast-track approval.

**Architecture:** `terms/services.py::publish_terms` closes the open range and inserts v+1 under a per-product
advisory lock and records TERMS_PUBLISHED. An outbox handler (`terms/handlers.py`) recomputes the affected items
and enqueues one Celery task per item; the task calls `terms/fanout.py::fan_out_item`, which does one item per
transaction: lock, re-check, `render_fast_track` → `create_version(FAST_TRACK)` (or no version on
`StaleTermsRef`) → `send_back(TERMS_CHANGED)`. Fast-track approval (`terms/fast_track.py`) is a thin wrapper over
E's `record_decision(lane=FAST_TRACK)` and `run_bulk`. The impact preview is a read-only selector that dry-runs
the same render against the proposed values.

**Tech stack:** Django 6 + ninja, Postgres 17 (advisory locks, EXCLUDE), Celery, pytest on real Postgres.

**Spec:** `docs/spec.md` §4.2 rulings 1, 2, 4, §4.3 "Offer terms", §6; `docs/product-spec.md` Automation "New
`OfferTerms` version"; `docs/decisions.md` "Approvals are tied to offer terms", "Rates are stored once";
`docs/plan/reports/{foundation,rules-engine,review-workflow}.md` (Interfaces).

## Global constraints

- State changes only in services, each with an Event in the same transaction. No raw dicts across boundaries.
- Lock order (E): item row lock, then `pg_advisory_xact_lock(ASSIGNMENT_LOCK_KEY)`; one item per transaction in
  any loop that calls `send_back`/`reopen_item`.
- Domain errors are typed (`core.errors`), mapped once; bulk skips are values (`run_bulk` → `BulkResult`).
- Time injected (`clock`). Legacy items are never fanned out (ruling 7).
- Offer terms are immutable (trigger); the only UPDATE allowed closes an open range, same lower bound/inclusivity.
- Env: `CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=clearpath-dev POSTGRES_PORT=55432
  REDIS_URL=redis://localhost:56379/0 CLEARPATH_TEST_DB_SUFFIX=wsF`.
- After API changes: `make schema`; commit `frontend/openapi/ninja.json` + `frontend/src/api/generated`.

## Rulings made here (reversible; report them)

1. **Publishing takes effect now.** `effective_from` is removed from `OfferTermsPublishIn`. `run_code_checks`
   links v+1's TermsRefs to the terms in effect *at check time*, so a future-dated version fanned out at publish
   would produce v+1 quoting the old version, which E's `stale_offer_terms` gate then refuses. Scheduling needs a
   beat job at the effective instant — cost if wrong: add the field back plus that job.
2. **Publishing identical values is refused** (422 on `values`): it would send every quoting item to re-review
   for nothing.
3. **Affected = approved, non-legacy, latest approving decision quotes a superseded version** (spec literal: an
   item quoting v12 is affected even if the fields it quotes didn't change; its generated v+1 then has no diff and
   one click clears it). The preview flags `numbers_change` per item so the lead sees this.
4. **The per-item task renders with the terms in effect when it runs**, not the event's: if v14 lands before
   v13's tasks drain, the item goes straight to v14 numbers. Idempotency falls out of the same check: once sent
   back, the item isn't `approved`; once fast-tracked, its approval quotes current terms.
5. **Generated version author and event actor = the lead who published** (`Version.author` is non-null).
6. **Bulk fast-track is lead-only** (product-spec Roles: leads do bulk actions); single fast-track is the
   assignee or a lead (E's `require_reviewer_of`). Impact preview and publish: lead only.

## Review Focus

1. A redelivered TERMS_PUBLISHED (or a re-run task) must not create a second v+1 or a second ITEM_REOPENED —
   `test_fan_out_is_idempotent_under_redelivery` (Task 2).
2. An item that the expiry sweep sent back between publish and task run must be left alone (no v+1 on an
   expired item) — `test_item_no_longer_approved_is_skipped` (Task 2).
3. A fan-out running next to a claim/sweep must not deadlock — Task 3's two concurrency tests, with a
   single-transaction control that does deadlock.
4. Copy whose changed number sits inside a dismissed finding's quote comes back open on v+1; bulk must skip it
   with `open_findings_block_decision`, not approve it — Task 4.
5. A publish for a product with no prior version (first version) must not fan out or fail — Task 1.

---

### Task 1: publish_terms service + API

**Files:** Create `backend/terms/services.py`, `backend/terms/tests/test_services.py`; modify
`backend/terms/api.py`, `backend/terms/schemas.py`, `backend/config/tests/test_contract.py` (drop the `/terms`
stub rows).

**Interfaces:**
- Produces: `publish_terms(*, actor: User, data: PublishTermsInput, clock: Clock = SYSTEM_CLOCK) -> int` (new
  OfferTerms id); `PublishTermsInput(product: Product, values: PersonalLoanTerms | CreditCardTerms, note: str = "")`;
  `TERMS_LOCK_BASE` advisory key per product. Event TERMS_PUBLISHED (entity OFFER_TERMS, actor lead,
  `TermsPublishedPayload(offer_terms_id, product, version, previous_offer_terms_id, affected_item_ids)`).

- [ ] Tests (red first): `test_publish_closes_previous_and_opens_new` (v1 upper == v2 lower == clock.now(); v2
  version 2, open-ended; event payload ids); `test_first_publish_has_no_previous`; `test_identical_values_refused`
  (InvalidInput on `values`); `test_values_product_must_match` (422); `test_only_leads_publish` (reviewer →
  NotPermitted); `test_affected_ids_recorded` (an approved item quoting v1 appears in `affected_item_ids`).
- [ ] Implement: `require_role(actor, LEAD)`; advisory lock on the product; current = `upper_inf` row
  (`select_for_update`); refuse equal values; close via `.update(effective_range=DateTimeTZRange(lower, now, "[)"))`;
  insert in a nested atomic, mapping `terms_no_overlap` to `TermsRangeOverlap`; record the event.
- [ ] API `POST /terms` → `Status(201, get_offer_terms(...))`, `ERRORS`; `test_api.py::test_publish_api_lead_only`.
- [ ] Commit.

### Task 2: affected-items selector + fan_out_item

**Files:** Create `backend/terms/fanout.py`, `backend/terms/tests/test_fanout.py`, `backend/terms/tests/conftest.py`
(re-export E's `pl_terms`, `submit`, `approve` fixtures; helper `publish(values)` and `go_live(item)`); extend
`backend/terms/selectors.py`.

**Interfaces:**
- Produces: `selectors.affected_approvals(*, product: Product, clock) -> tuple[AffectedApproval, ...]`,
  `AffectedApproval(item_id, approved_version_id, refs: tuple[TermsRefDraft, ...], quoted_terms_id)` — approved,
  non-legacy items of the product whose latest approving decision's version has TermsRefs to a non-current
  version. `fanout.fan_out_item(*, item_id: int, actor_id: int | None, clock) -> FanOutOutcome`
  (`StrEnum`: `reopened_fast_track | reopened_normal_lane | expired | expired_normal_lane | skipped`).
- [ ] Tests: `test_worked_example_generates_v2_with_recomputed_payment` ($10,000 / 36 months / 7.49% → publish
  apr_min 12.99 → v2 text has "12.99% APR" and "$337", origin fast_track, based_on v1, llm_check_status skipped,
  item needs_rereview(terms_changed), ITEM_REOPENED.generated_version_id == v2); `test_not_live_item_expires_with_generated_version`
  (expired(terms_changed); `start_new_round` without text gives v3 == v2 text);
  `test_stale_terms_ref_goes_to_normal_lane` (corrupt a ref's quoted_value → no new version, reopened with
  `generated_version_id=None`); `test_fan_out_is_idempotent_under_redelivery`; `test_item_no_longer_approved_is_skipped`;
  `test_legacy_and_other_products_untouched`.
- [ ] Implement `fan_out_item`: one `transaction.atomic()`: `locked_item`; skip unless approved, not legacy, the
  approval quotes a non-current version; render with the current terms; catch `StaleTermsRef` (decide here: normal
  lane); `create_version(FAST_TRACK, based_on=approved)`; `send_back(...)`.
- [ ] Commit.

### Task 3: outbox handler, task, concurrency

**Files:** Create `backend/terms/handlers.py`, `backend/terms/tasks.py`, `backend/terms/tests/test_handlers.py`.

**Interfaces:** `@handles(TERMS_PUBLISHED, name="terms.fan_out")` → `transaction.on_commit` enqueue of
`terms.fan_out_item(item_id, actor_id)` per id in `payload.affected_item_ids ∪ affected_approvals(product)`.
Task logs start/outcome/duration; autoretry on Exception.
- [ ] Tests: `test_handler_enqueues_one_task_per_affected_item` (`django_capture_on_commit_callbacks`, eager);
  `test_full_path_through_outbox` (publish → `dispatch_pending` + `deliver` → items moved);
  `test_fan_out_does_not_deadlock_against_a_concurrent_claim` (transaction=True, T1 paused inside item A's
  transaction holding the advisory lock; T2 claims another item and blocks on it; release; both finish);
  `test_per_item_transactions_avoid_deadlock_with_the_sweep` parametrized with a single-transaction control that
  raises `deadlock detected`.
- [ ] Commit.

### Task 4: fast-track approve (single + bulk)

**Files:** Create `backend/terms/fast_track.py`, `backend/terms/tests/test_fast_track.py`; API in
`backend/terms/api.py` (new `fast_track_router`, tag `decisions`); remove the stub from `backend/reviews/api.py`
(+ its schema import), register router in `backend/config/api.py`; contract test retarget.

**Interfaces:** `fast_track_approve(*, actor, item_id, version_n, reason, clock) -> DecisionResult`;
`bulk_fast_track_approve(*, actor, item_ids, reason, clock) -> BulkResult`. Endpoints
`POST /items/{int:item_id}/fast-track-approve` (`FastTrackIn{version_n, reason}` → 201 `DecisionOut`,
`fastTrackApprove`) and `POST /items/bulk/fast-track-approve` (`bulkFastTrackApprove`, 200 `BulkResultOut`).
- [ ] Tests: `test_one_click_approves_generated_version` (lane fast_track, `ai_review_carried_from` = v1, terms
  versions = [v2 terms]); `test_bulk_partial_success` (one clean, one with an open finding whose quote changed,
  one not fast-track → succeeded/skipped codes); `test_bulk_is_lead_only`; `test_reviewer_not_assigned_cannot_fast_track`;
  `test_diff_touches_only_numbers` (`records.version_diff` between v1 and v2: only inserted/deleted segments are
  the numbers).
- [ ] Commit.

### Task 5: impact preview + report

**Files:** `backend/terms/selectors.py` (`impact_preview`), `backend/terms/schemas.py` (`AffectedItemOut` gains
`lane: fast_track | normal`, `numbers_change: bool`; `ImpactPreviewOut.summary` copy), API, tests incl. a query
count that doesn't grow with items; `make schema`; `docs/plan/reports/offer-terms.md`.

**Interfaces:** `impact_preview(*, viewer, product, values, clock) -> ImpactPreview` (dataclass mirror of
`ImpactPreviewOut`). Copy: `"{n} approved items quote v{k}; {m} will need re-review"` + `"; {e} will expire"`
when e > 0; singular for 1; `"No approved items quote v{k}."` when 0.
- [ ] Tests: counts and split (live/not live), lane per item (StaleTermsRef → normal), `changed_fields`, partners
  with counts, writes nothing, lead only, query count flat.
- [ ] `make schema`, full verification (pytest, ruff, format, pyrefly, migrations check, frontend typecheck/tests).
- [ ] Commit; fresh reviewer; fix; PR.
