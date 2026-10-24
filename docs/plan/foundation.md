# Foundation (workstream 0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (chosen: native; the slice is
> tightly coupled) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every model and migration, the service/event/outbox pattern with one action end to end, typed domain
errors, `ItemFilter` + queue selector, and the full API contract the other twelve workstreams build against.

**Architecture:** One Django app per domain (`accounts`, `partners`, `terms`, `reviews`, `checks`, `audit`,
`notifications`; API-only skeletons `imports`, `exports`, `metrics`, `assistant`). Services are the only
writers and write state + `Event` in one transaction; selectors return frozen dataclasses; ninja routers are
thin and never catch domain errors. Invariants live in Postgres (CHECK, UNIQUE, EXCLUDE, immutability
triggers).

**Tech Stack:** Django 6.1, django-ninja 1.7.1, django-allauth 65.20 headless, Postgres 17 (btree_gist,
pg_trgm), Celery 5.6 beat, pydantic 2.14, pytest-django, orval.

**Spec:** `docs/spec.md` (§4.2 rulings, §6 standards), `docs/product-spec.md`, `docs/decisions.md`.

## Global Constraints

- Shared vocabulary comes from `core.domain`; new shared enums are added there, never redefined elsewhere.
- No raw dicts across boundaries: services take/return frozen dataclasses, selectors return dataclasses, API
  uses ninja `Schema`s. Event payloads are pydantic models, one per `EventType`.
- Endpoints contain no try/except; `DomainError` subclasses map to HTTP once, in `config/api.py`.
- Every operation has `operation_id` (camelCase) and exactly one tag from: items, findings, decisions, terms,
  partners, library, imports, exports, metrics, notifications, assistant, admin, me (health keeps `core`).
- Schema class names are globally unique (orval writes all models into one directory): suffix `In`/`Out`.
- Time is injected: services and time-relative selectors take `clock: Clock = SYSTEM_CLOCK`.
- `Event.type`, `Event.entity` are plain `CharField`s without `choices` so adding an event type never needs a
  migration in `audit`.
- Tests run on real Postgres with `CLEARPATH_TEST_DB_SUFFIX=ws0`; never touch the repo-root `.env`.
- No DB access at import time (the api-contract CI job exports the schema without a database).
- pyrefly `project-includes` lists every app.

## Review Focus

1. Concurrent dispatcher runs and commit-order gaps in the outbox: an event committed after a later-id event
   was dispatched must still be delivered (pinned by `test_cursor_does_not_skip_late_committing_event`).
2. Replay of the same event to the same handler applies once (pinned by
   `test_replayed_event_applies_handler_once`).
3. A mutation of an immutable row (Event, Version, Decision, Attachment) raises at the DB even via raw SQL
   (pinned by `test_*_rejects_update_and_delete`).
4. Keyset pagination across equal sort values (same priority, same `submitted_at`) neither repeats nor drops
   rows (pinned by `test_queue_keyset_pages_cover_all_rows_once`).
5. Overlapping terms ranges for one product fail with `TermsRangeOverlap`-mappable constraint name, while the
   same range on a different product succeeds (pinned by `test_offer_terms_exclusion_*`).

---

## Interfaces (the contract other workstreams consume)

### `core.domain` additions

```python
class PartnerStatus(StrEnum): ACTIVE="active"; PAUSED="paused"; TERMINATED="terminated"
class VersionOrigin(StrEnum): SUBMISSION="submission"; REVIEWER_EDIT="reviewer_edit"; FAST_TRACK="fast_track"
class DecisionLane(StrEnum): STANDARD="standard"; FAST_TRACK="fast_track"; REAFFIRM="reaffirm"
class TakedownState(StrEnum): REQUESTED="requested"; CONFIRMED="confirmed"
class DriftResult(StrEnum): UNCHANGED="unchanged"; MODIFIED="modified"; MISSING="missing"
class ExpiryRule(StrEnum): FIXED_MONTHS="fixed_months"; SEND_WINDOW="send_window"
class AssignmentMode(StrEnum): STICKY="sticky"; LOWEST_LOAD="lowest_load"; POOL="pool"; MANUAL="manual"; CLAIM="claim"; HANDOFF="handoff"
class NotificationKind(StrEnum): ASSIGNMENT="assignment"; DECISION="decision"; REREVIEW="rereview"; MENTION="mention"
class TermsField(StrEnum):  # what a TermsRef points at
    APR_MIN, APR_MAX, AMOUNT_MIN, AMOUNT_MAX, TERM_MONTHS, ORIGINATION_FEE_MIN_PCT, ORIGINATION_FEE_MAX_PCT,
    PURCHASE_APR_MIN, PURCHASE_APR_MAX, INTRO_APR, INTRO_MONTHS, BALANCE_TRANSFER_FEE_PCT, ANNUAL_FEE,
    EXAMPLE_AMOUNT, EXAMPLE_TERM_MONTHS, EXAMPLE_APR, EXAMPLE_PAYMENT   # values = lower-case names
class EntityType(StrEnum): ITEM, VERSION, FINDING, COMMENT, DECISION, PLACEMENT, ATTACHMENT, OFFER_TERMS,
    PARTNER, USER, IMPORT, EXPORT, EMAIL, SYSTEM
class EventType(StrEnum):   # value = dotted name
    ITEM_SUBMITTED="item.submitted"  ITEM_RESUBMITTED="item.resubmitted"  ITEM_ASSIGNED="item.assigned"
    ITEM_REVIEW_STARTED="item.review_started"  ITEM_FIELDS_UPDATED="item.fields_updated"
    ITEM_RISK_TIER_OVERRIDDEN="item.risk_tier_overridden"  ITEM_REOPENED="item.reopened"
    ITEM_EXPIRED="item.expired"  ITEM_WITHDRAWN="item.withdrawn"  ITEM_NEW_ROUND_STARTED="item.new_round_started"
    ITEM_IMPORTED="item.imported"  VERSION_CREATED="version.created"  CHECKS_COMPLETED="checks.completed"
    LLM_CHECK_REQUESTED="llm_check.requested"  LLM_CHECK_SUCCEEDED="llm_check.succeeded"
    LLM_CHECK_FAILED="llm_check.failed"  FINDING_ACCEPTED="finding.accepted"  FINDING_DISMISSED="finding.dismissed"
    FINDING_REOPENED="finding.reopened"  COMMENT_ADDED="comment.added"  DECISION_RECORDED="decision.recorded"
    PLACEMENT_RECORDED="placement.recorded"  PLACEMENT_UPDATED="placement.updated"
    TAKEDOWN_REQUESTED="placement.takedown_requested"  TAKEDOWN_CONFIRMED="placement.takedown_confirmed"
    ATTACHMENT_ADDED="attachment.added"  TERMS_PUBLISHED="terms.published"  PARTNER_CREATED="partner.created"
    PARTNER_UPDATED="partner.updated"  USER_AVAILABILITY_CHANGED="user.availability_changed"
    IMPORT_COMMITTED="import.committed"  EXPORT_CREATED="export.created"  EMAIL_SENT="email.sent"
    DEMO_RESET="demo.reset"
```

### `core.errors`

```python
class DomainError(Exception):
    code: ClassVar[str] = "domain_error"; status: ClassVar[int] = 400
    def __init__(self, message: str, *, details: Mapping[str, JsonValue] | None = None,
                 fields: Sequence[FieldIssue] = ()) -> None
@dataclass(frozen=True) class FieldIssue: loc: tuple[str | int, ...]; message: str; type: str = "invalid"
class InvalidInput(DomainError):      422 "invalid_input"   # + classmethod for_field(field: str, message: str)
class NotPermitted(DomainError):      403 "not_permitted"
class NotFound(DomainError):          404 "not_found"
class Conflict(DomainError):          409 "conflict"
class InvalidTransition(Conflict):    409 "invalid_transition"   # __init__(*, action: str, from_status: ItemStatus)
class OpenFindingsBlockDecision(Conflict): 409 "open_findings_block_decision"  # __init__(*, open_count: int)
class AiCheckPending(Conflict):       409 "ai_check_pending"
class TermsRangeOverlap(Conflict):    409 "terms_range_overlap"
class NotImplementedYet(DomainError): 501 "not_implemented"      # __init__(feature: str)
```
`config/api.py` registers handlers for `DomainError`, ninja `ValidationError` (→ 422 `validation_error`),
`AuthenticationError` (→ 401 `not_authenticated`), `HttpError` (→ its status, `http_error`). Body:
`core.schemas.ErrorOut {code: str, message: str, details: dict[str, JsonValue], fields: list[FieldErrorOut]}`;
`FieldErrorOut {loc: list[str|int], message: str, type: str}`. Response helpers in `core.schemas`:
`ERRORS: dict[frozenset[int], type[ErrorOut]]` (400, 401, 403, 404, 409, 422) and `STUB_ERRORS` (adds 501).
Usage: `response={200: ItemDetailOut, **ERRORS}`.

`core.db.constraint_name(exc: IntegrityError) -> str | None` (reads `exc.__cause__.diag.constraint_name`),
`core.db.forbid_mutation_sql(table: str) -> migrations.RunSQL` (row-level `BEFORE UPDATE OR DELETE` trigger
calling `core_forbid_mutation()`, created in `core/migrations/0002`). No TRUNCATE trigger: demo reset and
pytest flush TRUNCATE.

### `core.clock`

```python
class Clock(Protocol):
    def now(self) -> datetime: ...   # aware, UTC
    def today(self) -> date: ...     # timezone.localdate(now()) in settings.TIME_ZONE
class SystemClock: ...;  SYSTEM_CLOCK: Final = SystemClock()
@dataclass class FixedClock: at: datetime; def advance(self, delta: timedelta) -> None
```
Pytest fixture `clock` (root `conftest.py`) → `FixedClock(datetime(2026, 10, 24, 15, tzinfo=UTC))`.

### `core.permissions`

```python
IMPLIED_ROLES: Mapping[Role, frozenset[Role]] = {Role.LEAD: frozenset({Role.REVIEWER})}
def effective_roles(user: User) -> frozenset[Role]
def has_role(user: User, *roles: Role) -> bool         # any-of over effective roles
def require_role(user: User, *roles: Role) -> None     # raises NotPermitted
```
Stored `User.roles` is what was granted (SQL queries such as E's reviewer pool use it); permission checks use
effective roles, so a lead passes `require_role(user, Role.REVIEWER)` but is not in the auto-assignment pool
unless also granted `reviewer`.

### Models (app.Model: fields that matter to consumers)

- `accounts.User` (`AUTH_USER_MODEL`): `email` (login, case-insensitive unique), `display_name`, `roles:
  list[Role]` (CHECK contained in Role values), `is_available`, `last_assigned_at`, `is_active`, `is_staff`.
- `partners.Partner`: `name` (unique ci), `type: PartnerType`, `status: PartnerStatus`, `website`,
  `contact_email`, `agreement_signed_on`, `notes`, `created_at`, `updated_at`.
- `terms.OfferTerms`: `product`, `version` (unique per product), `effective_range: DateTimeTZRange` (`[)`),
  `values` (JSONB; `typed_values -> PersonalLoanTerms | CreditCardTerms`; validated on `save()`), `note`,
  `created_by`, `created_at`. Constraints: `terms_no_overlap` (EXCLUDE gist product =, effective_range &&),
  `terms_values_product_matches`, `terms_range_not_empty`.
- `reviews.ReviewItem`: `title, product, channel, partner, markets, owner, assignee, assigned_at, status,
  round, risk_tier, risk_tier_overridden, is_prescreen, is_legacy, legacy_ref (unique, null), legacy_submitter,
  legacy_reviewer, legacy_history, llm_check_status, tags, notes, reopen_reason, planned_first_run,
  planned_last_run, source_url, current_version, open_findings_count, submitted_at, approved_at,
  approval_expires_at, retention_until, created_at, updated_at, queue_priority (generated)`; property `key`
  → `"CP-<id>"`. `queue_priority = (0 if needs_rereview else 10) + {high:0, medium:1, low:2}[risk_tier]`.
- `reviews.Version`: `item, n (unique per item), content_text, content_sha256, author, origin: VersionOrigin,
  based_on, created_at, search_vector (generated tsvector 'english')`; immutable (trigger);
  `Version.hash_content(text) -> str`.
- `reviews.Comment`: `version, author, body, span_start, span_end, mentions (M2M User), created_at`.
- `reviews.Attachment`: exactly one of `item | version | partner | decision` (CHECK `attachment_one_owner`),
  `kind, file, original_name, content_type, size_bytes, sha256, uploaded_by, uploaded_at`; immutable.
- `reviews.Decision`: `item, version, outcome, lane, approver, reason, ruleset_date, expires_at,
  llm_override_reason, ai_review_carried_from (Version), decided_at`, `terms_versions` (M2M via
  `DecisionTermsVersion`), `evidence` (via `DecisionEvidence(decision, attachment, sha256)`); immutable.
- `reviews.Placement`: `item, approved_version, location, url, first_run, last_run, monitored, takedown_state,
  takedown_requested_at, takedown_confirmed_at, created_by, created_at`. Live = `first_run <= today <=
  coalesce(last_run, ∞)` and `takedown_state` is not confirmed (`reviews.selectors.live_placements_q(today)`).
- `reviews.Snapshot` (stretch M): `placement, fetched_at, text, result: DriftResult, diff`.
- `reviews.ExpiryPolicy`: `channel (unique), rule: ExpiryRule, months`; seeded by data migration.
- `reviews.SavedView`: `owner, name, filters (ItemFilter JSON), sort, columns`.
- `checks.Finding`: `version, rule_id, citation, source, severity, state, span_start, span_end, quote,
  message, suggested_fix, reason, resolved_by, resolved_at, carried_from, created_at`.
- `checks.TermsRef`: `version, offer_terms, field: TermsField, span_start, span_end, quote, quoted_value`.
- `checks.CheckRun`: `version, source, status, content_sha256, ruleset_key, started_at, finished_at,
  findings_count, dropped_findings_count, model, input_tokens, output_tokens, error`.
- `audit.Event`: `id, type, entity, entity_id, item, actor, at, from_status, to_status, payload, txid`;
  append-only (trigger). `audit.OutboxCursor(name, last_txid, last_event_id)`, `audit.ProcessedEvent(event,
  handler, processed_at)` unique `(event, handler)`.
- `notifications.Notification`: `user, kind, item, event, message, read_at, created_at`; unique `(event,
  user)`. `notifications.OutboxEmail`: `to, subject, body, item, requested_by, approved_by, thread_id, sent_at`.

### `checks.contracts` (engine-facing types; C and D build against these)

```python
@dataclass(frozen=True) class Span: start: int; end: int          # 0 <= start < end, else ValueError
@dataclass(frozen=True) class CheckInput:
    text: str; product: Product; channel: Channel; markets: frozenset[Market]
    attachment_kinds: frozenset[AttachmentKind]; is_prescreen: bool; has_partner: bool
    offer_terms: PersonalLoanTerms | CreditCardTerms | None
@dataclass(frozen=True) class FindingDraft:
    rule_id: str; citation: str; source: FindingSource; severity: Severity; message: str
    suggested_fix: str = ""; span: Span | None = None; quote: str | None = None
@dataclass(frozen=True) class TermsRefDraft: field: TermsField; span: Span; quote: str; value: Decimal
@dataclass(frozen=True) class CodeCheckResult:
    findings: tuple[FindingDraft, ...]; terms_refs: tuple[TermsRefDraft, ...]; ruleset_key: str
```
Seam: `checks.services.run_code_checks(*, version: Version, clock: Clock) -> CodeCheckResult` currently
returns an empty result (`ruleset_key="none"`) and persists nothing; workstream C/E plug the engine in here.

### `audit` (events + outbox)

```python
# audit/payloads.py
class EventPayload(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")
class ItemSubmittedPayload(EventPayload): version_id: int; version_n: int; round: int; risk_tier: RiskTier; content_sha256: str
class ItemAssignedPayload(EventPayload): assignee_id: int | None; previous_assignee_id: int | None; mode: AssignmentMode; reason: str
...one class per EventType...
PAYLOADS: Mapping[EventType, type[EventPayload]]   # completeness asserted by a test

# audit/services.py
def record_event(*, type: EventType, entity: EntityType, entity_id: int, payload: EventPayload,
                 actor: User | None, at: datetime, item_id: int | None = None,
                 from_status: ItemStatus | None = None, to_status: ItemStatus | None = None) -> Event
    # RuntimeError outside transaction.atomic; TypeError if payload isn't PAYLOADS[type]

# audit/outbox.py
@dataclass(frozen=True) class EventRecord:
    id: int; type: EventType; entity: EntityType; entity_id: int; item_id: int | None
    actor_id: int | None; at: datetime; from_status: ItemStatus | None; to_status: ItemStatus | None
    payload: EventPayload        # parsed through PAYLOADS[type]
Handler = Callable[[EventRecord], None]
class HandlerRegistry:
    def register(self, *types: EventType, name: str) -> Callable[[Handler], Handler]
    def for_type(self, type: EventType) -> tuple[HandlerSpec, ...]
    def get(self, name: str) -> HandlerSpec
REGISTRY: Final = HandlerRegistry();  handles = REGISTRY.register
def dispatch_pending(*, registry: HandlerRegistry = REGISTRY, enqueue: Enqueue = enqueue_handler,
                     batch_size: int = 500) -> DispatchResult(events: int, deliveries: int)
def deliver(*, event_id: int, handler_name: str, registry: HandlerRegistry = REGISTRY) -> Delivery  # APPLIED | DUPLICATE
def redeliver_stale(*, registry=REGISTRY, enqueue=enqueue_handler, clock=SYSTEM_CLOCK,
                    older_than=timedelta(minutes=5), lookback=timedelta(days=1)) -> int
```
Registration: each app's `handlers.py` (autodiscovered in `AuditConfig.ready`) uses
`@handles(EventType.X, name="<app>.<stable_name>")`. `name` is the idempotency key, so it never changes.
A handler runs inside `transaction.atomic()` together with its `ProcessedEvent` insert; DB side effects are
exactly-once, external side effects (LLM call) should enqueue their own idempotent task. Celery:
`audit.tasks.dispatch_outbox` (beat, 2 s), `audit.tasks.run_event_handler(event_id, handler_name)` (autoretry
with backoff), `audit.tasks.redeliver_stale_events` (beat, 5 min).

Gap-free cursor: `Event.txid` defaults to `pg_current_xact_id()`; the dispatcher reads events ordered by
`(txid, id)` past the cursor with `txid < pg_snapshot_xmin(pg_current_snapshot())` (or its own transaction),
so an event from a still-open transaction is never skipped.

### `reviews.services` (reference action + small real actions)

```python
@dataclass(frozen=True) class SubmitItemInput:
    title: str; product: Product; channel: Channel; markets: tuple[Market, ...]; content_text: str
    planned_first_run: date; planned_last_run: date | None = None; partner_id: int | None = None
    is_prescreen: bool = False; source_url: str | None = None; tags: tuple[str, ...] = ()
@dataclass(frozen=True) class SubmitItemResult:
    item_id: int; version_id: int; version_n: int; status: ItemStatus; risk_tier: RiskTier
    llm_check_status: CheckStatus; event_id: int
def submit_item(*, actor: User, data: SubmitItemInput, clock: Clock = SYSTEM_CLOCK) -> SubmitItemResult
def update_item_fields(*, actor: User, item_id: int, changes: ItemFieldChanges, clock=SYSTEM_CLOCK) -> None
def add_comment(*, actor: User, item_id: int, data: NewComment, clock=SYSTEM_CLOCK) -> int
def add_attachment(*, actor: User, owner: AttachmentOwner, kind: AttachmentKind, file: UploadedFile, clock=SYSTEM_CLOCK) -> int
```
`reviews.risk.derive_risk_tier(*, product, channel, has_partner, is_prescreen) -> RiskTier` (ruling 5: partner
channels or any partner, mortgage, prescreen → high; paid_social/paid_search/display/landing_page → medium;
else low). Seams left for E inside `submit_item`: assignment under the advisory lock (comment
`# Seam (E): assign_on_submit`); D picks up `ITEM_SUBMITTED` via an outbox handler.

### `reviews.filters` + selectors

```python
class ItemFilter(Schema):  # also the saved-view JSON and the export/assistant filter
    q: str | None; status: list[ItemStatus]; product: list[Product]; channel: list[Channel]
    partner_id: list[int]; assignee_id: list[int]; owner_id: list[int]; mine: bool; submitted_by_me: bool
    unassigned: bool; risk_tier: list[RiskTier]; market: list[Market]; tag: list[str]
    is_legacy: bool | None; has_open_findings: bool | None; reopen_reason: list[ReopenReason]
    submitted_after: datetime | None; submitted_before: datetime | None; waiting_more_than_days: int | None
    run_from: date | None; run_to: date | None
class ItemSort(StrEnum): QUEUE="queue"; OLDEST="oldest"; NEWEST="newest"; UPDATED="updated"; TITLE="title"
def filter_items(*, viewer: User, filters: ItemFilter, clock: Clock = SYSTEM_CLOCK) -> QuerySet[ReviewItem]
def list_items(*, viewer, filters, sort=ItemSort.QUEUE, cursor: str | None = None, limit: int = 50, clock=...) -> ItemPage
@dataclass(frozen=True) class ItemPage: rows: tuple[ItemRow, ...]; next_cursor: str | None
@dataclass(frozen=True) class ItemRow: id, key, title, product, channel, status, round, risk_tier,
    reopen_reason, llm_check_status, is_legacy, tags, open_findings_count, submitted_at, updated_at,
    current_version_n, partner: PartyRef | None, owner: PartyRef | None, assignee: PartyRef | None
def queue_stats(*, viewer, clock=...) -> QueueStats
def find_phrase(*, viewer, phrase: str, filters: ItemFilter, limit: int = 20, clock=...) -> tuple[SearchHit, ...]
def search_text(*, viewer, query: str, filters: ItemFilter, limit: int = 20, clock=...) -> tuple[SearchHit, ...]
```
`filter_items` is the one place an `ItemFilter` becomes SQL (`filter_items` is what G's export and K's tools
call). `reviews.diff.diff_texts(old: str, new: str) -> tuple[DiffSegment, ...]` (word-level).

### API surface

Router per app, mounted at `/api/` in `config/api.py`. Real = implemented; stub = validates input, raises
`NotImplementedYet` (501), owner workstream in brackets.

- me: `GET /me` getMe, `PATCH /me` updateMe (availability) — real.
- admin: `GET /users` listUsers real; `POST /admin/users` createUser, `PATCH /admin/users/{id}` updateUser
  stub; `POST /admin/demo/reset` resetDemo stub [L].
- items: `GET /items` listItems, `GET /items/stats` getQueueStats, `POST /items` submitItem,
  `GET /items/{id}` getItem, `PATCH /items/{id}` updateItem, `GET /items/{id}/versions` listVersions,
  `GET /items/{id}/versions/{n}` getVersion, `GET /items/{id}/diff` getVersionDiff, `GET /items/{id}/history`
  getItemHistory, `GET/POST /items/{id}/comments` listComments/addComment, `GET/POST /items/{id}/attachments`
  listItemAttachments/uploadItemAttachment, `GET /attachments/{id}/download` downloadAttachment,
  `GET /items/{id}/placements` listPlacements, `GET/POST/DELETE /views` savedViews — real.
  Stubs: `POST /items/fetch-url` fetchCopyFromUrl [I/D], `POST /items/{id}/versions` resubmitItem,
  `POST /items/{id}/claim` claimItem, `POST /items/{id}/assign` assignItem, `POST /items/bulk/assign`
  bulkAssignItems, `POST /items/{id}/new-round` startNewRound, `POST /items/{id}/placements` recordPlacement,
  `PATCH /placements/{id}` updatePlacement, `POST /placements/{id}/confirm-takedown` confirmTakedown [E].
- findings: `GET /items/{id}/findings` listFindings real; stubs `POST /findings/{id}/accept|dismiss|reopen`
  [E], `POST /checks/preview` previewChecks [C], `POST /items/{id}/llm-check/retry` retryLlmCheck [D].
- decisions: `GET /items/{id}/decisions` listDecisions real; stubs `POST /items/{id}/decisions` recordDecision,
  `POST /items/{id}/reaffirm` reaffirmApproval, `POST /items/{id}/pull` pullItem,
  `POST /items/bulk/fast-track-approve` bulkFastTrackApprove [E/F].
- terms: `GET /terms` listOfferTerms, `GET /terms/current` getCurrentOfferTerms, `GET /terms/{id}`
  getOfferTerms real; stubs `POST /terms/impact-preview` previewTermsImpact, `POST /terms` publishOfferTerms [F].
- partners: `GET /partners` listPartners, `GET /partners/{id}` getPartner, `POST /partners` createPartner,
  `PATCH /partners/{id}` updatePartner, `GET/POST /partners/{id}/attachments` — real.
- library: `GET /library` listLibrary, `GET /library/search` searchLibrary (`mode=phrase|text`) — real.
- exports: stubs `POST /exports` createExport, `GET /exports/{id}` getExport, `GET /items/{id}/evidence-pack`
  getEvidencePack [G].
- imports: stubs `POST /imports` uploadImport, `POST /imports/sample` loadSampleImport, `GET /imports/{id}`
  getImport, `PUT /imports/{id}/mapping` setImportMapping, `GET /imports/{id}/preview` getImportPreview,
  `POST /imports/{id}/commit` commitImport [G].
- metrics: stubs `GET /metrics/summary` getMetricsSummary, `GET /metrics/series` getMetricSeries [E/N].
- notifications: `GET /notifications` listNotifications, `POST /notifications/{id}/read`
  markNotificationRead, `POST /notifications/read-all` markAllNotificationsRead, `GET /outbox` listOutboxEmails,
  `GET /outbox/{id}` getOutboxEmail — real.
- assistant: stubs `POST /assistant/threads` createAssistantThread, `GET /assistant/threads/{id}`
  getAssistantThread, `POST /assistant/threads/{id}/messages` streamAssistantReply (SSE;
  `text/event-stream` of `AssistantStreamEventOut` = token | tool_call | tool_result | approval_required |
  done | error), `POST /assistant/threads/{id}/approvals/{interrupt_id}` resolveAssistantApproval [K].

---

## Tasks

### Task 1: Accounts, settings, auth round trip

**Files:** Create `backend/accounts/{__init__,apps,models,managers,admin,api,schemas,services,selectors}.py`,
`backend/accounts/migrations/0001_initial.py`, `backend/accounts/tests/test_{models,auth}.py`, `backend/conftest.py`.
Modify `backend/config/settings/{base,test}.py`, `backend/pyproject.toml` (pyrefly includes), `config/api.py`.

**Interfaces:** Produces `accounts.models.User`, `GET /api/me` → `MeOut{id, email, display_name, roles,
is_available}`, fixtures `user_factory(roles=..., email=...)`, `clock`.

- [ ] Test DB suffix: `test.py` sets `DATABASES["default"]["TEST"]["NAME"] = f"test_{NAME}_{suffix}"` from
  `Env.clearpath_test_db_suffix`; verify with `pytest --create-db -q` and `psql -l | grep test_clearpath_ws0`.
- [ ] Failing tests: `test_email_is_login_and_case_insensitive_unique`, `test_roles_check_rejects_unknown_role`
  (raw UPDATE → IntegrityError), `test_headless_login_then_me` (POST
  `/_allauth/browser/v1/auth/login` `{email, password}` → 200, then `GET /api/me` → 200 with roles),
  `test_me_requires_session` (401 with `code="not_authenticated"`).
- [ ] Implement User (AbstractBaseUser + PermissionsMixin, `USERNAME_FIELD="email"`), manager lower-cases
  email; settings `AUTH_USER_MODEL`, `ACCOUNT_USER_MODEL_USERNAME_FIELD = None`; `/me` router.
- [ ] Run accounts tests → PASS; commit.

### Task 2: core cross-cutting (errors, clock, permissions, db helpers, handlers)

**Files:** Create `backend/core/{errors,clock,permissions,db}.py`, `core/migrations/0002_forbid_mutation_function.py`,
`core/tests/test_{errors,clock,permissions}.py`. Modify `core/schemas.py`, `config/api.py`, `core/domain.py`.

- [ ] Failing tests: `test_domain_error_maps_to_status_and_envelope` (temporary router raising
  `OpenFindingsBlockDecision(open_count=2)` → 409 `{code: "open_findings_block_decision", details:
  {open_count: 2}}`), `test_validation_error_uses_envelope` (422, `code="validation_error"`, `fields[0].loc`),
  `test_not_implemented_is_501`, `test_require_role_lead_implies_reviewer`,
  `test_require_role_raises_not_permitted`, `test_fixed_clock_advance`.
- [ ] Implement per Interfaces; add domain enums.
- [ ] PASS; commit.

### Task 3: partners + terms models

**Files:** `backend/partners/*`, `backend/terms/*` (models, migrations, tests).

- [ ] Failing tests: `test_offer_terms_exclusion_rejects_overlap_same_product` (IntegrityError,
  `constraint_name == "terms_no_overlap"`), `test_offer_terms_exclusion_allows_other_product`,
  `test_offer_terms_values_validated_on_save` (inverted APR → pydantic ValidationError),
  `test_offer_terms_values_product_must_match_column` (raw SQL → IntegrityError), `test_partner_name_unique_ci`.
- [ ] Implement; migration depends on `("core", "0001_postgres_extensions")`. PASS; commit.

### Task 4: reviews models

**Files:** `backend/reviews/{models,risk}.py`, migrations `0001_initial`, `0002_immutability_triggers`,
`0003_seed_expiry_policy`; `reviews/tests/test_models.py`.

- [ ] Failing tests: `test_version_unique_per_item_n`, `test_version_rejects_update_and_delete`,
  `test_decision_rejects_update_and_delete`, `test_attachment_requires_exactly_one_owner` (0 and 2 owners
  fail), `test_affiliate_item_requires_partner_unless_legacy`, `test_legacy_ref_unique_but_nullable`,
  `test_queue_priority_generated` (needs_rereview+low < submitted+high), `test_search_vector_generated`,
  `test_comment_span_check`, `test_placement_last_run_not_before_first`, `test_expiry_policy_seeded_for_every_channel`.
- [ ] Implement models, indexes (queue partial, assignee queue partial, title trigram, tags GIN, version
  search GIN, version content trigram), triggers via `forbid_mutation_sql`. PASS; commit.

### Task 5: checks models + contracts + seam

**Files:** `backend/checks/{models,contracts,services}.py`, migrations, tests.

- [ ] Failing tests: `test_finding_span_must_be_ordered`, `test_finding_quote_iff_span`,
  `test_dismissed_finding_needs_reason`, `test_finding_unique_per_version_rule_span` (null spans collide),
  `test_span_rejects_inverted`, `test_terms_ref_span_check`.
- [ ] Implement. PASS; commit.

### Task 6: audit events, outbox, notifications

**Files:** `backend/audit/{models,payloads,services,outbox,tasks,apps}.py`, migrations (incl. append-only
trigger), `backend/notifications/{models,handlers,services,selectors}.py`, tests; settings
`CELERY_BEAT_SCHEDULE`.

- [ ] Failing tests: `test_every_event_type_has_payload`, `test_event_rejects_update_and_delete`,
  `test_record_event_requires_atomic`, `test_record_event_rejects_wrong_payload_type`,
  `test_replayed_event_applies_handler_once` (deliver twice → one Notification, second returns DUPLICATE),
  `test_dispatch_enqueues_each_handler_and_advances_cursor`, `test_dispatch_twice_does_not_redeliver`,
  `test_cursor_does_not_skip_late_committing_event` (transactional: open txn A inserts event, txn B inserts and
  commits, dispatch sees only B's after A commits? — dispatch before A commits delivers nothing past A's
  txid; after A commits both are delivered), `test_redeliver_stale_requeues_missing_receipts`,
  `test_assignment_notification_handler`, `test_mention_notification_handler`.
- [ ] Implement. PASS; commit.

### Task 7: submit_item + small services

**Files:** `backend/reviews/services.py`, `reviews/tests/test_services.py`, `reviews/tests/test_risk.py`.

- [ ] Failing tests: `test_derive_risk_tier` (parametrized over the ruling-5 table),
  `test_submit_item_creates_item_v1_and_event` (status submitted, round 1, v1 hash, `llm_check_status=pending`,
  one `item.submitted` event with `to_status="submitted"`, same transaction),
  `test_submit_requires_marketer`, `test_submit_affiliate_without_partner_is_invalid_input`,
  `test_submit_rolls_back_event_on_failure`, `test_update_item_fields_risk_tier_needs_reviewer_role`,
  `test_add_comment_records_event_with_mentions`, `test_add_attachment_hashes_file`.
- [ ] Implement. PASS; commit.

### Task 8: ItemFilter, queue selector, search, diff, other selectors

**Files:** `backend/reviews/{filters,selectors,search,diff}.py`, `partners/selectors.py`, `terms/selectors.py`,
tests.

- [ ] Failing tests: `test_queue_order_rereview_then_tier_then_age`, `test_queue_keyset_pages_cover_all_rows_once`,
  `test_list_items_query_count_constant` (`django_assert_num_queries(1)` at 3 and 30 rows),
  `test_filter_mine_unassigned_waiting`, `test_find_phrase_matches_case_insensitive`,
  `test_search_text_websearch_ranked`, `test_diff_texts_word_level`, `test_bad_cursor_is_invalid_input`.
- [ ] Implement. PASS; commit.

### Task 9: API contract

**Files:** `backend/{accounts,reviews,checks,terms,partners,notifications}/api.py` + `schemas.py`,
`backend/{imports,exports,metrics,assistant}/{__init__,apps,api,schemas}.py`, `config/api.py`,
`*/tests/test_api.py`.

- [ ] Failing tests: `test_submit_item_api_round_trip` (201 → `GET /items/{id}`), `test_list_items_api_filters`
  (`?status=submitted&status=in_review`), `test_every_operation_has_id_and_known_tag` (walk
  `api.get_openapi_schema()`), `test_stub_endpoints_return_501_envelope` (one per stub router),
  `test_marketer_cannot_update_risk_tier_api` (403 envelope).
- [ ] Implement routers. PASS; commit.

### Task 10: demo users, schema, frontend

**Files:** `backend/accounts/management/commands/seed_demo_users.py`, `.env.example`,
`frontend/openapi/ninja.json`, `frontend/src/api/generated/**`.

- [ ] Failing test `test_seed_demo_users_idempotent` (4 users, each role, password from env; rerun keeps 4),
  `test_seed_demo_users_requires_password`.
- [ ] Implement; `make schema`; frontend `npm run typecheck && npm run test:run && npm run lint`; second
  `make schema` → no diff. Commit.

### Task 11: review, report, PR

- [ ] Fresh reviewer subagent over `git diff main...`; fix valid findings; save to
  `docs/plan/reviews/foundation.md`.
- [ ] Full verification; write `docs/plan/reports/foundation.md`; push; open PR.
