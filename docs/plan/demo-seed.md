# Demo seed and Reset demo (workstream L) Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans), then one fresh whole-branch reviewer.
> **Why not subagent-driven:** every task writes into one story DSL (`demo/story.py`) and one runner
> (`demo/runner.py`), and the catalog's copy is tuned against the runner's real service calls; parallel
> implementers would each have to re-learn E/F/D2/G's service contracts to write a few dozen lines.

**Goal:** `manage.py seed_demo [--reset]` and an admin-only "Reset demo" button produce a realistic ClearPath
compliance team on a fresh database: one login per role plus extra reviewers, partners with agreements, versioned
offer terms, ~45 native items across every reachable status with real copy and real triage history backdated over
~10 weeks, deterministic AI pre-review results, and the sample tracker imported as legacy history.

**Architecture:** a new `demo` app. `demo/content/*` is a catalog of frozen dataclasses (people, partners, terms,
item stories: copy versions plus timed steps). `demo/runner.py` merges every story's steps into one timeline,
sorts by time, and executes each step through the existing service functions with a `FixedClock` set to the
step's backdated instant; after each step it drains the outbox in-process (`dispatch_pending` + `deliver`), and
completes any requested AI check with a scripted chat model (`demo/ai.py`) through `checks.prereview.claim` /
`attempt`. `demo/reset.py` wraps TRUNCATE (domain tables, RESTART IDENTITY) + seed in one transaction under an
advisory lock, with the on-commit task seams set to no-ops, so a failure leaves the previous demo intact and
nothing leaks to the real worker. `POST /admin/demo/reset` records a `DemoReset` row and enqueues the Celery job
on commit; `GET /admin/demo/resets/{id}` reports its status.

**Tech stack:** Django 6 + ninja, Postgres 17, Celery, pytest on real Postgres; React + TanStack Query, React Aria.

**Spec:** `docs/spec.md` §1 Users, §2, §3 ("seeded demo logins, one per role"), §4.2, §4.3, §5.4, §5.7, §8.1 L,
§9 ("which demo content to seed, as long as it exercises every rule family and every status");
`docs/product-spec.md`; `docs/plan/reports/{foundation,rules-engine,review-workflow,offer-terms,import-export,
llm-wiring}.md`; `samples/README.md`; `docs/plan/ledger.md` Rulings.

## Global Constraints

- Seed THROUGH services: every row a service writes (items, versions, findings, decisions, placements, comments,
  attachments, terms, partners, import) comes from the service call; no hand-inserted domain rows.
- Time is injected: every service call gets the runner's `FixedClock`; no step is in the future of seed time.
- The AI never approves; AI findings are warnings (DB constraint). Seeded AI results are scripted and labeled
  model `demo-seed` (no live calls during seeding).
- `draft` is unreachable (E: intake has no drafts); not hand-inserted. Reported as a deviation.
- Demo logins keep the `@clearpath.demo` domain (frontend `SignIn.tsx`, e2e fixtures). Password from
  `DEMO_USER_PASSWORD`, defaulting to a documented demo password so a fresh environment works.
- Personas reuse the sample tracker's names (`scripts/generate_sample_tracker.py`) so `legacy_reviewer` strings
  match real users and partner history joins legacy and native items.
- Copy: §5.4 one term per concept; AI messages read as suggestions, never "violation".
- Env: `CLEARPATH_ENV_FILE="" DJANGO_SECRET_KEY=t POSTGRES_PASSWORD=clearpath-dev POSTGRES_PORT=55432
  REDIS_URL=redis://localhost:56379/0 CLEARPATH_TEST_DB_SUFFIX=wsL`. Never touch the repo-root `.env`.
- After the API change: `make schema`; commit `frontend/openapi/ninja.json` + `frontend/src/api/generated`.

## Review Focus

1. Reset while the beat dispatcher and worker are running: no seeded event may reach the real LLM handler (a live
   model call per seeded version). Test: after `reset_demo`, every seeded event has a receipt for every matching
   handler, and `prereview.enqueue` / `terms.tasks.enqueue_fan_out` / `imports.services._enqueue_commit` were
   never called with the real implementations.
2. Reset that fails midway (bad password, a story step refused by a gate) must leave the previous demo intact.
   Test: a reset with a broken catalog raises and the item count is unchanged.
3. The admin who clicks Reset stays signed in (users and sessions are not truncated; demo users are upserted).
   Test: API reset as admin, then `GET /api/me` with the same client is 200.
4. Two resets requested at once: the second POST returns the in-flight job rather than starting another. Test.
5. Seed run on a database that already has data and no `--reset`: no-op with a message, not duplicates. Test.

---

### Task 1: Story DSL, catalog skeleton, and the rule-coverage test

**Files:** Create `backend/demo/{__init__,apps}.py`, `demo/story.py`, `demo/content/{__init__,people,items_*}.py`,
`demo/tests/test_catalog.py`. Modify `config/settings/base.py` (INSTALLED_APPS += "demo").

**Interfaces (Produces):**
- `story.Persona(key, email, name, roles, login: bool)`; `story.PartnerSpec(key, name, type, website,
  contact_email, agreement_signed_on, notes, agreement_text)`; `story.TermsSpec(product, at, values, note)`.
- `story.Story(key, owner, title, product, channel, markets, versions: tuple[str, ...], steps, partner=None,
  prescreen=False, tags=(), first_run_days, last_run_days, attachments=())`, steps are frozen dataclasses with
  `at: Ago` (`Ago(days, hours=0, minutes=0)` relative to seed time): `Submit`, `Resubmit(v, note)`,
  `NewRound(v)`, `Claim`, `Assign(to, reason)`, `Triage(rule_id, accept|dismiss, text, quote=None)`,
  `Comment(by, body, mentions)`, `Decide(outcome, reason, edited=None, override=None)`, `Place(location, url,
  first_run, last_run)`, `Pull(reason)`, `ConfirmTakedown`, `Reaffirm(reason)`, `FastTrack(reason)`,
  `Drift`, `Attach(kind, name, body)`. Submissions carry `ai: AiScript` (`Clean | Findings(...) | Outage |
  Pending`).
- `content.CATALOG: Catalog(personas, partners, terms, stories, globals)`.

- [ ] Step 1: `test_every_code_rule_fires_on_some_seeded_version`: for every story version build a `RuleContext`
  (product, channel, markets, partner type, attachment kinds, terms in effect at the version's submit time) and
  run `checks.engine.run_code_checks`; assert the union of rule ids ⊇ every `kind == "code"` rule in `RULES`.
  Plus `test_clean_copy_exists` (≥ 5 versions with zero code findings) and `test_every_ai_quote_is_in_its_text`.
- [ ] Step 2: write the catalog until both pass (iterate copy with the engine).
- [ ] Step 3: commit.

### Task 2: Runner: timeline, services, outbox drain, scripted AI

**Files:** Create `demo/runner.py`, `demo/ai.py`, `demo/seed.py`, `demo/tests/test_seed.py`.

**Interfaces:** `ai.ScriptedReviewModel(findings)` (GenericFakeChatModel subclass with `bind_tools`);
`seed.seed_demo(*, now: datetime, password: str) -> SeedResult(items: int, legacy_items: int, users: int)`;
`runner.Runner(clock).run(catalog)`.

- [ ] Step 1: tests (DB): `test_seed_counts_per_status` (every status but draft present, exact counts),
  `test_every_item_has_events`, `test_every_code_rule_fires_on_a_persisted_version` (Finding rows),
  `test_ai_results_are_persisted_succeeded_failed_pending`, `test_legacy_import_matches_readme_totals` (178),
  `test_terms_history_v1_v2` and `test_fast_track_version_exists`.
- [ ] Step 2: implement; Step 3: commit.

### Task 3: Reset, management command, Celery job, API

**Files:** Create `demo/models.py` (+ migration), `demo/reset.py`, `demo/tasks.py`,
`demo/management/commands/seed_demo.py`, `demo/schemas.py`, tests. Modify `accounts/api.py` (replace the stub),
`accounts/schemas.py` (`DemoResetOut`), `accounts/management/commands/seed_demo_users.py` (delegates to
`demo.users`), `config/tests/test_contract.py` (stub list), `.env.example`.

- [ ] Tests: idempotent second `seed_demo`; `--reset` restores the same `{title: (key, status)}` map; reset
  rollback on failure; admin-only (403 for lead); admin stays signed in; second POST returns the in-flight job;
  receipts for every handler on every seeded event.

### Task 4: Shell button

**Files:** `frontend/src/ui/layout/UserMenu.tsx` (+ test). Admin-only "Reset demo…" → `ModalDialog
role="alertdialog"` confirm → `useResetDemo` → poll `getDemoReset` every 1 s until done/failed → toast and
`queryClient.resetQueries()`.

### Task 5: Docs, run the stack, screenshots

`docs/demo.md` (logins, 5-minute path per role), `docs/plan/reports/demo-seed.md`; fresh DB + `seed_demo`, dev
frontend + backend, screenshot each role's first screen at 1440x900 into `docs/plan/reviews/ui/demo/`; fix
implausible seed content; PR "Demo seed and Reset demo".
