# Foundation (workstream 0): report

Branch `ws0/foundation`, closes #1. Plan: `docs/plan/foundation.md`. Review and resolutions:
`docs/plan/reviews/foundation.md`.

## What was built

- **Custom user model** `accounts.User` (`AUTH_USER_MODEL = "accounts.User"`): email login (stored lower-cased,
  unique), `display_name`, `roles: list[Role]` (no DB CHECK, so a new role is an addition, not a migration),
  `is_available`, `last_assigned_at`.
  allauth headless logs in by email; a test logs in through `/_allauth/browser/v1/auth/login` and calls
  `/api/me`. **Existing dev databases migrated with `auth.User` must be recreated** (`docker compose down -v`
  or drop the `clearpath` DB). This worktree used a private `clearpath_ws0` DB and never touched the shared one.
- **All domain models and migrations**: accounts, partners, terms, reviews, checks, audit, notifications. The
  API-only apps imports, exports, metrics, assistant have no models yet (their owners add them).
- **Invariants in Postgres**: `terms_no_overlap` EXCLUDE; insert-only triggers on `audit_event`,
  `reviews_version`, `reviews_decision`, `reviews_decisiontermsversion`, `reviews_decisionevidence`,
  `reviews_attachment`; `terms_offerterms_guard` (offer terms immutable except closing an open range; no
  DELETE); composite FKs `decision_version_same_item`, `placement_version_same_item`,
  `item_current_version_same_item` against `version_id_item_unique (id, item_id)`; CHECKs for spans, run dates,
  exactly-one attachment owner, partner on partner channels, `needs_rereview` carries a `reopen_reason`,
  decision reasons and approval expiry, finding triage records; unique keys listed under Interfaces.
- **No `choices=` on any model field** (a test enforces it): adding a member to a `core.domain` enum needs no
  migration in any app. Enums are enforced at the schema edge and in services.
- **Indexes**: partial queue index `(queue_priority, submitted_at, id) WHERE status IN (submitted, in_review,
  needs_rereview)` and its assignee variant; trigram GIN on `UPPER(title::text)` and `UPPER(content_text)`
  (the expression Django's `icontains` compiles to; an EXPLAIN test proves the planner uses them); GIN on tags;
  generated `english` tsvector on version content with GIN; event outbox/item/entity/type indexes.
- **Patterns**: typed domain errors + one set of exception handlers; injectable clock; role checks;
  `submit_item` end to end; event payload registry; gap-free outbox with idempotent handlers; `ItemFilter` +
  keyset queue selector; a query-count test on 22 read operations, every real list plus the detail reads that
  embed lists (24 cases, data grown between two
  measurements); precedent search; word diff.
- **API contract** for every screen, with `operation_id` and one tag per operation; regenerated
  `frontend/openapi/ninja.json` and `frontend/src/api/generated` (health badge test unchanged and passing).
- **Demo users**: `manage.py seed_demo_users` → `marketer@`, `reviewer@`, `lead@`, `admin@clearpath.demo`,
  password from `DEMO_USER_PASSWORD` (validated; added to `.env.example`).
- **Per-worktree test DB**: the scaffold commit claimed `CLEARPATH_TEST_DB_SUFFIX` support but `test.py` didn't
  have it; it does now (`test_<db>_<suffix>`).

## Interfaces other workstreams need

### Shared vocabulary (`core.domain`, added)

`PartnerStatus`, `VersionOrigin` (submission | reviewer_edit | fast_track), `DecisionLane` (standard |
fast_track | reaffirm), `TakedownState` (requested | confirmed), `DriftResult`, `ExpiryRule` (fixed_months |
send_window), `AssignmentMode` (sticky | lowest_load | pool | manual | claim | handoff), `NotificationKind`,
`TermsField` (PL/CC schema field names plus `example_amount|term_months|apr|payment`), `EntityType`,
`EventType` (dotted values, e.g. `item.submitted`; full list in `core/domain.py`).

### Errors, clock, permissions

```python
# core.errors — raise from services; never catch in endpoints
DomainError(message, *, details: Mapping[str, JsonValue] | None = None, fields: Sequence[FieldIssue] = ())
InvalidInput (422 invalid_input; InvalidInput.for_field("partner_id", "…"))   NotPermitted (403 not_permitted)
NotFound (404 not_found; NotFound.entity("item", 12))   Conflict (409 conflict)
InvalidTransition(*, action: str, from_status: ItemStatus)   OpenFindingsBlockDecision(*, open_count: int)
AiCheckPending()   TermsRangeOverlap(message)   NotImplementedYet(feature: str)  (501)
# body for every non-2xx: core.schemas.ErrorOut {code, message, details, fields: [FieldErrorOut{loc, message, type}]}
# ninja validation errors -> 422 code "validation_error"; no session -> 401 "not_authenticated"
# response dict fragments: response={200: X, **ERRORS} (real) / {**STUB_ERRORS} (adds 501)
core.db.constraint_name(exc: IntegrityError) -> str | None     # map e.g. "terms_no_overlap" -> TermsRangeOverlap
core.db.forbid_mutation(table) -> RunSQL                         # insert-only trigger for a migration

# core.clock
Clock (Protocol): now() -> aware UTC datetime; today() -> date in settings.TIME_ZONE
SYSTEM_CLOCK; FixedClock(at).advance(delta); pytest fixture `clock` = 2026-10-24 15:00 UTC

# core.permissions
IMPLIED_ROLES = {LEAD: {REVIEWER}}; REVIEW_ROLES = (Role.REVIEWER,)
effective_roles(user) -> frozenset[Role]; has_role(user, *roles) -> bool; require_role(user, *roles) -> None
```

Stored `User.roles` is what was granted; SQL pools (E's auto-assignment) query stored roles, so a lead is not
auto-assigned unless also granted `reviewer`. Inactive users have no effective roles.

### Models (fields others write or query)

- `reviews.ReviewItem`: `status, round, risk_tier, risk_tier_overridden, is_prescreen, reopen_reason (E clears
  it when a re-review resolves or a new round starts from expired; queue priority keys on it),
  llm_check_status, is_legacy, legacy_ref (unique, null), legacy_submitter, legacy_reviewer, legacy_history,
  owner (null only if legacy), assignee, assigned_at, current_version, open_findings_count (denormalized:
  the action that persists or triages findings writes it), submitted_at, approved_at, approval_expires_at,
  retention_until, planned_first_run/last_run, tags, notes, markets, source_url ("" if none),
  queue_priority (generated: 0 + tier if `reopen_reason` is set and status is queued, else 10 + tier)`.
  `tags` are 1-50 characters each (422 otherwise). Display key: `item.key` → `CP-<id>`.
  `reviews.models.QUEUE_STATUSES`. `current_version` must be a version of the same item (composite FK).
- `reviews.Version` (insert-only): `item, n, content_text, content_sha256 (Version.hash_content(text)), author,
  origin, based_on, created_at, search_vector`.
- `reviews.Decision` (insert-only; `version` must belong to `item`): `item, version, outcome, lane, approver, reason (non-blank), ruleset_date,
  expires_at (required for approvals), llm_override_reason ("" if none), ai_review_carried_from, decided_at`;
  `DecisionTermsVersion(decision, offer_terms)`; `DecisionEvidence(decision, attachment, sha256)`.
- `reviews.Attachment` (insert-only): exactly one of `item|version|partner|decision`; `kind, file, sha256, …`.
- `reviews.Placement` (`approved_version` must belong to `item`): `first_run, last_run (null = open), takedown_state/requested_at/confirmed_at, monitored`.
  Live: `reviews.selectors.live_placements_q(today, prefix="")`.
- `reviews.ExpiryPolicy(channel unique, rule, months)` seeded: email/sms/direct_mail send_window;
  landing_page/call_script 12; affiliate_page/paid_social/paid_search/display 6.
- `reviews.SavedView(owner, name, filters: ItemFilter JSON, sort, columns)`; `reviews.Snapshot` (stretch M).
- `checks.Finding`: `version, rule_id, citation, source, severity, state, span_start/end, quote (null iff no
  span), message, suggested_fix, reason (required to dismiss), resolved_by/at (required unless open),
  carried_from (only on dismissed)`; unique `(version, source, rule_id, span_start, span_end)` nulls not distinct.
- `checks.TermsRef(version, offer_terms, field: TermsField, span_start, span_end, quote, quoted_value)`;
  an approved item quotes v12 if its *approved* version (latest approving Decision's version) has TermsRefs to
  v12; not its current version, which moves on once fast-track generates v+1.
- `checks.CheckRun(version, source, status, content_sha256, ruleset_key, started_at, finished_at,
  findings_count, dropped_findings_count, model, input_tokens, output_tokens, error)`; cache index on
  `(content_sha256, source, ruleset_key)`.
- `terms.OfferTerms(product, version, effective_range [from, to), values, note, created_by, created_at)`;
  `.typed_values`; values validated on save. Immutable (trigger): the only allowed UPDATE closes an open-ended
  range (same lower bound, every other column unchanged); DELETE is refused.
- `notifications.Notification(user, kind, item, event, message, read_at, created_at)` unique `(event, user)`;
  `notifications.OutboxEmail(to[], subject, body, item, requested_by, approved_by, thread_id, sent_at)`.

### The code-check seam (on C's engine types)

The engine's own types (`checks.engine`: `RuleContext`, `CheckResult`, `FindingDraft`, `TermsRefDraft`, `Span`;
merged with C in #21) are the contract. This branch's earlier `checks.contracts` duplicated them and was removed
on rebase; nothing merged imported it.

Seam: `checks.services.run_code_checks(*, version, clock) -> PersistedChecks(result: checks.engine.CheckResult,
open_findings_count)` is called inside `submit_item`'s transaction and returns `PersistedChecks.empty()` today.
The integration (C/E; owner still to be named, see Open risks): build a `RuleContext` from the item and the
current OfferTerms, call `checks.engine.run_code_checks`, persist Findings (`suggested_fix or ""`), TermsRefs
(`TermsField(draft.field)`) and a CheckRun keyed by `ENGINE_VERSION`, carry dismissals, record
`CHECKS_COMPLETED`, and return the open count after carry-forward. The calling action (submit, resubmit) writes
it to `ReviewItem.open_findings_count`, so each action has one writer. `checks/tests/test_engine_compat.py` fails
if the engine emits a terms field `TermsField` doesn't know, or a rule id or citation longer than the `Finding`
columns.

### Events and the outbox

```python
audit.services.record_event(*, type: EventType, entity: EntityType, entity_id: int, payload: EventPayload,
                            actor: User | None, at: datetime, item_id: int | None = None,
                            from_status: ItemStatus | None = None, to_status: ItemStatus | None = None) -> Event
# RuntimeError outside transaction.atomic(); TypeError unless payload is audit.payloads.PAYLOADS[type]
audit.payloads: one model per EventType (ItemSubmittedPayload, ItemAssignedPayload(assignee_id, previous_assignee_id,
  mode, reason), DecisionRecordedPayload(...), …); FieldChange(field, before, after); parse_payload(type, data)
  ItemImportedPayload(import_id, legacy_ref, row_number, timeline: LegacyTimeline(submitted_at, first_reviewed_at,
    decided_at, outcome, rounds))   # all optional, dates validated in order; G fills it, metrics reads it
  UserCreatedPayload(user_id, email, roles) / UserRolesChangedPayload(user_id, before, after) /
    UserActiveChangedPayload(user_id, is_active)   # for the admin user-management services
audit.outbox:
  @handles(EventType.X, EventType.Y, name="<app>.<stable_name>")   # in <app>/handlers.py, autodiscovered
  def handler(event: EventRecord) -> None: ...                    # runs in a transaction with its receipt
  EventRecord(id, type, entity, entity_id, item_id, actor_id, at, from_status, to_status, payload: EventPayload)
  dispatch_pending(*, registry=REGISTRY, enqueue=enqueue_handler, batch_size=500) -> DispatchResult(events, deliveries, busy)
    # skip_locked: returns busy=True at once if another dispatcher holds the cursor
  deliver(*, event_id, handler_name, registry=REGISTRY) -> Delivery.APPLIED | Delivery.DUPLICATE
  redeliver_stale(*, registry, enqueue, clock, older_than=5 min, lookback=1 day) -> int
Celery: audit.dispatch_outbox (beat 2 s), audit.run_event_handler(event_id, handler_name) (autoretry, backoff),
        audit.redeliver_stale_events (beat 5 min)
```

- Adding an `EventType` needs a payload model (a test enforces it) but no migration.
- `name` is the idempotency key: never rename a deployed handler. DB side effects are exactly-once; a handler
  with an external call (D's LLM check) should enqueue its own idempotent task.
- Registered handlers: `notifications.assignment` (ITEM_ASSIGNED → assignee; `mode=pool` → active leads;
  `mode=sticky` → "back for your review", which is how resubmissions notify the reviewer, so E must record the
  sticky ITEM_ASSIGNED that decisions.md rule 1 implies; a manual unassign notifies nobody), `notifications.mention`
  (COMMENT_ADDED → mentioned users), `notifications.decision` (DECISION_RECORDED → owner),
  `notifications.rereview` (ITEM_REOPENED → owner + assignee). The actor is never notified of their own action.
- D: register `@handles(EventType.ITEM_SUBMITTED, EventType.ITEM_RESUBMITTED, …, name="checks.llm_prereview")`.

### Services and selectors

```python
reviews.services.submit_item(*, actor, data: SubmitItemInput, clock=SYSTEM_CLOCK) -> SubmitItemResult
  SubmitItemInput(title, product, channel, markets: tuple, content_text, planned_first_run, planned_last_run=None,
                  partner_id=None, is_prescreen=False, source_url=None, tags=())
  SubmitItemResult(item_id, version_id, version_n, status, risk_tier, llm_check_status, open_findings_count, event_id)
  # Seam (E) comment marks where assign_on_submit goes, under the advisory lock, inside the transaction.
reviews.services.update_item_fields(*, actor, item_id, changes: ItemFieldChanges(tags, notes, risk_tier), clock)
reviews.services.add_comment(*, actor, item_id, data: NewComment, clock) -> int
reviews.services.add_attachment(*, actor, owner: AttachmentOwner("item"|"version"|"partner", id), kind, file, clock)
  -> AttachmentRef(id, sha256)
reviews.services.create_saved_view / delete_saved_view; partners.services.create_partner / update_partner;
accounts.services.update_me; notifications.services.mark_read / mark_all_read
reviews.risk.derive_risk_tier(*, product, channel, has_partner, is_prescreen) -> RiskTier

reviews.filters.ItemFilter  (q, status[], product[], channel[], partner_id[], assignee_id[], owner_id[], mine,
  submitted_by_me, unassigned, risk_tier[], market[] (any), tag[] (all), is_legacy, has_open_findings,
  reopen_reason[], submitted_after/before, waiting_more_than_days, approved_after/before, approved_within_days,
  run_from/run_to)
reviews.filters.ItemSort: queue | oldest | newest | updated | title
  # sort=queue with no status filter means the queue statuses (submitted, in_review, needs_rereview)
reviews.selectors.filter_items(*, viewer, filters, clock) -> QuerySet[ReviewItem]   # G's export, K's tools
reviews.selectors.list_items(*, viewer, filters, sort, cursor, limit, clock) -> ItemPage(rows: tuple[ItemRow], next_cursor)
reviews.selectors.get_item_row, row_queryset, item_row, queue_stats -> QueueStats
reviews.search.search_library(*, viewer, query, mode, filters, limit, clock) -> SearchResults(mode, query, hits)
reviews.search.find_phrase(*, viewer, phrase, filters, limit, clock) / search_text(*, viewer, query, filters, limit, clock)
  -> tuple[SearchHit]  (snippet: tuple[SnippetPart(text, highlighted)], version_outcome/version_decided_at: the
  matched version's own latest decision, not the item's)
reviews.records: get_item_detail, list_versions, get_version, version_diff, item_history -> ItemHistory, list_comments,
  list_item_attachments, list_partner_attachments, list_placements(is_live), list_decisions, list_saved_views
reviews.diff.diff_texts(old, new) -> tuple[DiffSegment(op, text)]
checks.selectors.list_findings; terms.selectors.list_offer_terms / current_offer_terms / get_offer_terms;
partners.selectors.list_partners / get_partner_detail / repeat_issues; notifications.selectors.*
```

### API (`/api/…`, tag in brackets; [stub → owner])

- [me] `GET /me`, `PATCH /me` · [users] `GET /users` (pickers, any role) · [admin] `POST /admin/users`,
  `PATCH /admin/users/{id}`
  [stub → admin], `POST /admin/demo/reset` [stub → L]
- [items] `GET /items` (default `sort=queue` without `status` = the queue), `GET /items/stats`, `POST /items`, `GET|PATCH /items/{id}`, `GET /items/{id}/versions`,
  `GET /items/{id}/versions/{n}`, `GET /items/{id}/diff?from_n&to_n`, `GET /items/{id}/history` (typed: one
  `…EventOut` per event type, discriminated on `type`), `GET|POST /items/{id}/comments`,
  `GET|POST /items/{id}/attachments`, `GET /attachments/{id}/download`, `GET /items/{id}/placements`,
  `GET|POST /views`, `DELETE /views/{id}`. Stubs → E: `POST /items/{id}/versions` (resubmit), `/claim`,
  `/assign`, `/items/bulk/assign`, `/new-round`, `POST /items/{id}/placements`, `PATCH /placements/{id}`,
  `/placements/{id}/confirm-takedown`; → I/M: `POST /items/fetch-url`.
- [findings] `GET /items/{id}/findings`; stubs `POST /findings/{id}/accept|dismiss|reopen` → E,
  `POST /checks/preview` → C, `POST /items/{id}/llm-check/retry` → D.
- [decisions] `GET /items/{id}/decisions`; stubs `POST /items/{id}/decisions`, `/reaffirm`, `/pull` → E,
  `POST /items/bulk/fast-track-approve` → F.
- [terms] `GET /terms`, `GET /terms/current`, `GET /terms/{id}`; stubs `POST /terms/impact-preview`,
  `POST /terms` → F.
- [partners] `GET|POST /partners`, `GET|PATCH /partners/{id}`, `GET|POST /partners/{id}/attachments`.
- [library] `GET /library` (approved, incl. legacy), `GET /library/search?mode=phrase|text&query=` + ItemFilter.
- [exports] stubs → G: `POST /exports`, `GET /exports/{id}`, `GET /items/{id}/evidence-pack`.
- [imports] stubs → G: `POST /imports` (file), `POST /imports/sample`, `GET /imports/{id}`,
  `PUT /imports/{id}/mapping`, `GET /imports/{id}/preview`, `POST /imports/{id}/commit`.
- [metrics] stubs: `GET /metrics/summary`, `GET /metrics/series` (owner not assigned in spec §8.1; see risks).
- [notifications] `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all`,
  `GET /outbox`, `GET /outbox/{id}`.
- [assistant] stubs → K: `POST /assistant/threads`, `GET /assistant/threads/{id}`,
  `POST /assistant/threads/{id}/messages` and `POST /assistant/threads/{id}/approvals/{interrupt_id}`. Both
  stream SSE: each `data:` line is one `AssistantStreamEventOut` (`token | tool_call | tool_result |
  approval_required | done | error`, discriminated on `type`).

### Conventions learned the hard way (copy these)

- **Return lists, not tuples, from list endpoints.** ninja reads any returned 2-tuple as `(status, body)`, so a
  selector's tuple of exactly two rows becomes a 500. Return `list(selector(...))`; use `Status(201, body)`
  (`from ninja import Status`) for non-200 codes (bare tuples are deprecated in ninja 1.7).
- **Integer path params use `{int:name}`** so `/items/bulk/…` and `/terms/impact-preview` don't match `/{id}`.
- **Model defaults and conditions use `Enum.MEMBER.value`** so migrations hold plain strings, and **model
  fields carry no `choices=`** (`core/tests/test_model_conventions.py`).
- **Endpoints never return a raw dict**: return a selector dataclass or an `…Out` instance
  (`test_no_operation_returns_a_raw_dict`).
- **`openapi_extra` response keys are ints** (`200`), or `make schema --sorted` crashes.
- **File params use `ninja.UploadedFile`**, not Django's.
- Pyrefly doesn't see `<fk>_id` attributes or reverse relations across string FKs; those lines carry targeted
  `# pyrefly: ignore[missing-attribute]`.

## Verification

Run after the review fix pass and a rebase onto `origin/main` (which brought in C's engine, #21, and the design
system's frontend dependencies), at the head of `ws0/foundation` (test DB suffix `ws0`; private dev DB
`clearpath_ws0`). The 621 backend tests are this branch's 295 plus the engine's 326; the frontend counts
include the design system's tests.

```
$ uv run pytest -q
621 passed in 7.66s
$ uv run --group lint ruff check .
All checks passed!
$ uv run --group lint ruff format --check .
172 files already formatted
$ uv run --group typecheck pyrefly check
 INFO 0 errors (93 suppressed, 1 warning not shown, use `--min-severity=warn` to see it)
$ manage.py makemigrations --check --dry-run
No changes detected
$ manage.py check --fail-level WARNING
System check identified no issues (0 silenced).
$ make schema && git status --porcelain -- frontend/openapi frontend/src/api/generated
(no drift)
$ npm run typecheck
tsc -b: ok
$ npm run test:run
 Test Files  12 passed (12)
      Tests  145 passed (145)
$ npm run lint
eslint: ok
$ npm run format:check
All matched files use Prettier code style!
exit status: 0
```

Also, on a freshly dropped and recreated `clearpath_ws0`: `manage.py migrate` applied every migration through
`reviews.0006_version_same_item` and `terms.0003_offer_terms_immutable`, and `seed_demo_users` created the four
demo users. Tests that must fail without their fix were run RED first: the query-count test was checked by
removing two prefetches (history 7 -> 19 queries, comments 5 -> 9), the trigram test by EXPLAIN before the
index change, and the dispatcher test blocked for the holder's full 3 s before `skip_locked`.

## Deviations from the spec and brief, and why

- **Queue order** keys "re-reviews of live content first" on `reopen_reason IS NOT NULL AND status IN
  (submitted, in_review, needs_rereview)`, not an `Exists` over placements: a stored generated `queue_priority`
  keeps the partial index and keyset cursor stable. The first version keyed on `status = needs_rereview` and
  lost priority as soon as a reviewer opened the item (review Important 1). Cost: E must clear `reopen_reason`
  when a re-review resolves and when a new round starts from `expired`; a stale reason ranks a fresh round high.
- **Outbox cursor is `(txid, id)` below the snapshot horizon**, not `id > cursor`. An id cursor skips an event
  whose transaction commits after a higher id was dispatched; the concurrency test fails against an id-only
  cursor (`[2] == [1, 2]`). Cost: a long-open transaction delays dispatch until it ends.
- **`is_prescreen` on ReviewItem**: ruling 5 makes prescreen high-risk at intake, and nothing else carries that
  fact. It's an intake field beyond the "minimum fields" list.
- **Extra ReviewItem fields** (`legacy_submitter/reviewer/history`, `risk_tier_overridden`, timestamps) and
  models (`ExpiryPolicy` seeded, `SavedView`, `Snapshot`, `CheckRun`, `OutboxEmail`) so E/F/G/D/K/M don't need
  migrations in apps they don't own.
- **Search snippets are structured parts, not HTML**: `ts_headline` doesn't escape untrusted affiliate copy.
- **`MeOut.effective_roles`** beside `roles`, so the frontend gates UI without re-implementing role implication.
- **More real endpoints than the minimum** (comments, attachments, saved views, partners CRUD, notifications,
  typed history, search) where they were thin over services/selectors.
- **Health stays tagged `core`** (the scaffold's tag; the badge test imports `generated/core`).
- **Read receipts and saved views write no Event**: they're per-user UI state, not domain state.

## Open risks

- **Needs your call: who may read attachments** (review Important 10). `GET /attachments/{id}/download` and the
  `download_url`s in `getPartner` and the item/decision attachment lists check only that the caller is signed in,
  so a marketer can download partner agreements and decision evidence, while uploading partner attachments is
  Lead-only. The spec doesn't settle read access. Options: (a) keep "any staff reads everything" (matches the
  queue's "no status chasing" visibility; zero work); (b) partner attachments Lead+ only, item and decision
  evidence readable by anyone who can read the item (one check in `records.get_attachment` and in the
  partner selectors). I'd pick (b); nothing is changed until you decide.
- **Needs your call: does the library include lapsed approvals?** `GET /library` forces `status=[approved]`, so
  items approved once and now `expired`, `needs_rereview` or `withdrawn` drop out of the "approved archive". For
  precedent search a lapsed approval is still precedent; for "what's approved to run" it is not.

- **Dev DB recreate**: anyone with a `clearpath` DB migrated under `auth.User` must recreate it after merge.
- **Unowned integrations**: (a) wiring C's engine into `run_code_checks` and persisting findings, (b) metrics
  endpoints (spec §8.1 assigns metrics to no workstream; E or N?), (c) admin user management and
  `fetch-url`. Need orchestrator rulings.
- **Snapshot horizon is cluster-wide**: a long transaction in any database on the same Postgres server holds
  back dispatch. Fine on RDS with one app DB; in local dev, a stuck shell transaction pauses the outbox.
- **Redelivery has no dead-letter**: a handler that always fails is re-enqueued every 5 minutes for a day,
  then dropped silently except for logs.
- **Queue perf at 50k items** is designed for (partial index, row-value keyset, one query per page) but not yet
  proven with `EXPLAIN ANALYZE` (spec §6.3); that needs the 50k seed.
- **Attachment storage** is local `MEDIA_ROOT`; production needs S3 storage and presigned downloads
  (workstream A/G). `download_url` points at the API view today.
