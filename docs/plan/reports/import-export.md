# Import, export, and evidence packs (workstream G): report

Branch `wsG/import-export`, closes #8. Plan: `docs/plan/import-export.md` (native execution; why is in its
header). Review and resolutions: `docs/plan/reviews/import-export.md`.

## What was built

- **Import** (`backend/imports/`): upload an xlsx or "Load sample tracker" → columns guessed → admin edits the
  column, status-value, and value mappings → preview (every row's action and every problem, as values) → commit
  as a Celery job. Commit creates legacy items (`is_legacy`, `legacy_ref`, no versions, no decisions), creates
  missing Partners-sheet partners, and records one `ITEM_IMPORTED` per item carrying `LegacyTimeline`, plus
  `PARTNER_CREATED` per partner and one `IMPORT_COMMITTED`. Idempotent: a committed job is never re-run, and
  refs already in the app are skipped (`already_imported`), so a second import of the same file creates nothing.
- **Export** (`backend/exports/`): xlsx of any filtered view (an `ItemFilter` plus the view's sort), built by a
  Celery job, stored through Django storage under a random name, downloaded only through `downloadExport` by its
  requester or an admin. Optionally a zip with an evidence pack per approved item in the view (max 200).
- **Evidence pack**: `getEvidencePack` returns the record as JSON; `createEvidencePack` builds the zip as a job:
  `summary.txt`, `approved-version-vN.txt`, `decision.json` (decision + every finding on that version with its
  triage), `offer-terms/<product>-vN.json` (the quoted terms snapshot + the quoted spans), `evidence/<id>-<name>`
  (the files the decision relied on), `history.json`, `manifest.json` (hash recorded at decision vs. hash now,
  per file), `SHA256SUMS` (`sha256sum -c SHA256SUMS` verifies the pack).
- **Sample workbook** bundled at `backend/imports/sample/clearpath_review_tracker.xlsx` (the Docker build context
  is `backend/`); a test keeps it cell-identical to `samples/`.

## Mapping and normalization

Column guesses (`imports/mapping.py`, first match wins; the admin can change any of them):

| Tracker column | Target | Stored on |
|---|---|---|
| Request ID | `legacy_ref` | `ReviewItem.legacy_ref` (`-b`, `-c`… for a reused ID) |
| Date Submitted | `submitted_on` | `submitted_at` (00:00 UTC), `LegacyTimeline.submitted_at` |
| Submitter / BU | `submitter` | `legacy_submitter` |
| Product | `product` | `product` |
| Channel | `channel` | `channel` |
| Asset Name / File Link | `title` | `title` (display text or text before the URL), `source_url` (hyperlink target or the URL in the text) |
| Affiliate / Partner | `partner` | `partner` (resolved or created) |
| Risk Tier | `risk_tier` | `risk_tier` (sheet value; derived via `derive_risk_tier` only when unmapped/unknown) |
| Trigger Terms Present (Y/N) | `trigger_terms` | `notes` line + `ImportRow.parsed` (no `ReviewItem` column) |
| Assigned Reviewer | `reviewer` | `legacy_reviewer` |
| Version # | `version_number` | `notes` line + `ImportRow.parsed` |
| Revision Round | `rounds` | `round`, `LegacyTimeline.rounds` |
| Status | `status` | `status`; outcome → `LegacyTimeline.outcome` |
| Reviewer Comments / Required Changes | `comments` | `legacy_history` verbatim; segments → first_reviewed_at / decided_at |
| Approval Date & Approver | `approval` | `approved_at`; approver → `notes` line |
| Approval Expiration / Re-review Date | `expires_on` | `approval_expires_at` (approved rows) |
| Live URL / Placement & Screenshot Link | `placement` | `notes` line + `ImportRow.parsed.placement_urls` |

Value normalization (keys are case- and whitespace-insensitive; every string cell is stripped on read):

| Field | Raw → app value | Unknown value |
|---|---|---|
| Status | Not Started, Pending → submitted; In Review → in_review; Changes Requested, Changes Req., Needs changes → changes_requested (outcome changes_requested); Approved → approved/approved; Approved w/ Changes, Approved - minor edits → approved/approved_with_edits; Rejected → rejected/rejected. Blank + approval cell → approved/approved (warning); blank otherwise → submitted (info) | `unmapped_status` error; admin maps it (`status_values`) to submitted/in_review/changes_requested/approved/rejected |
| Product | PL, Personal Loan, personal loans → personal_loan; CC, Credit Card → credit_card; MTG, Mortgage Prequal → mortgage_prequal (and the enum values) | `unknown_value` error; `value_mappings` |
| Channel | the nine Lists labels → snake_case enum | `unknown_value` error; `value_mappings` |
| Risk tier | High/Medium/Low | warning; derived |
| Trigger terms | Y, yes → true; N, no → false; blank, `?` → null + warning | `unknown_value` warning, null; `value_mappings` (yes/no) |
| Partner | key = casefold, drop spaces/punctuation; then a unique prefix (`CardPerks` → `CardPerks Weekly`); app spellings win over sheet spellings; any spelling change is a `fuzzy_partner` warning | `unknown_partner` error; `value_mappings` to a known partner |
| Dates | Excel dates; `M/D/YY` (20YY), `M/D/YYYY`, ISO, `Mon D` (year from `MCR-YY-`) → `coerced_date` info | `unparseable_date` (error for Date submitted, warning for expiry) |
| Comment dates | `R<n> <M>/<D> <II>:` segments; year starts at the submission year, +1 whenever the month goes backwards | invalid date → warning, segment skipped |
| Approval | `M/D/YY - F. Last`; `F. Last` only → date from the last segment (`derived_approval_date` warning); approver resolved by initial + last name against the Lists reviewers | `unresolved_approver` warning |
| Rows | column A not ref-shaped (no spaces, ≥1 digit) → `not_data_row`, skipped; same ref + same (title, submitted) or identical cells → `duplicate_row`, skipped; same ref otherwise → `-b` + `reused_ref` warning | |

Severity: **error** blocks the row (skipped at commit, or commit refused with `skip_rows_with_problems=false`);
**warning** imports with a note; **info** a value read from a non-standard form. Timeline dates out of order →
`inconsistent_dates` error.

## Oracle coverage (each mess → test)

Tests read `samples/README.md` itself (`imports/tests/oracle.py` parses its tables), so a regenerated sample moves
the expectations with it; `test_readme_totals_are_the_ones_asserted_here` pins the hard-coded totals to the README
text. All in `backend/imports/tests/test_normalize.py` unless noted.

| README section | Test (parametrized cases) |
|---|---|
| Expected import totals (180 rows, 179 with ID, 1 note, 1 dup, 178 items, 177 IDs, date range, 16 open / 8 unassigned, status table) | `test_expected_import_totals`, `test_expected_status_totals`; on Postgres: `test_services.py::test_sample_commit_matches_the_readme_totals`, `::test_each_item_gets_an_imported_event_carrying_its_timeline` |
| Status spelling variants | `test_status_spelling_variants` (27) |
| Product spelling variants | `test_product_spelling_variants` (34) |
| Date Submitted / Expiration stored as text | `test_dates_stored_as_text_are_coerced_and_noted` (18) |
| Approval cell with approver only | `test_approver_only_takes_the_date_from_the_last_round` (6) |
| Approved row with blank expiration | `test_approved_with_blank_expiration_stays_null` (6), `test_missing_expiry_is_reported_on_exactly_the_oracle_rows` |
| Exact duplicate row | `test_exact_duplicate_row_is_one_item` |
| Request ID reused | `test_reused_request_id_is_two_items_with_a_disambiguated_ref` |
| Leading / trailing whitespace | `test_every_string_cell_is_stripped` (9) |
| Partner typed differently | `test_partner_typed_differently_resolves_and_is_reported` (4) |
| Trigger Terms Y/N variants | `test_trigger_terms_variants` (13) |
| Merged note row | `test_merged_note_row_is_skipped_and_reported` |
| Links: hyperlink objects vs text (112/45/22 asset, 23/72 placement, 7 labelled) | `test_asset_links_from_hyperlinks_text_or_nothing`, `test_placement_links_from_hyperlinks_and_text` |
| Every raw value, mapped (Status 15, Product 8, Trigger 6, Partner 13) | `test_every_status_value`, `test_every_product_value`, `test_every_trigger_terms_value`, `test_every_partner_value` |
| Comments that cross New Year | `test_comments_that_cross_new_year_roll_the_year` |
| Reviewer hand-offs | `test_hand_offs_keep_the_assigned_reviewer` |
| Version # = Round + 1 / five-round items / revision-round rule | `test_rounds_follow_the_comment_segments` |
| Approval date = last segment's date, approver = its reviewer | `test_approval_date_equals_the_last_round_on_every_approved_row` (all 145) |
| Past-expiry approvals import as approved | `test_services.py::test_sample_commit_matches_the_readme_totals` (145 approved) |

Mutation check: deleting the `"needs changes"` alias, or disabling unique-prefix matching, each fails 8 tests.

## Interfaces for the frontend (J)

Tags `imports` and `exports`; generated hooks in `frontend/src/api/generated/{imports,exports}`.

**Import (admin only; 403 otherwise).**

| Operation | Request | Response |
|---|---|---|
| `listImports` `GET /imports` | | `ImportJobSummaryOut[]`, 20 newest |
| `uploadImport` `POST /imports` | multipart `file` | 201 `ImportJobOut`; 422 `invalid_input` on `body.file` if not a readable xlsx (≤5 MB, ≤5,000 data rows, used range ≤10,000 rows below the header) |
| `loadSampleImport` `POST /imports/sample` | | 201 `ImportJobOut` |
| `getImport` `GET /imports/{id}` | | `ImportJobOut`: `status` (uploaded → mapped → committing → committed / failed), `columns[]` {name, sample_values, suggested_field, field}, `status_values[]` {source_value, rows, status, outcome, source: default/mapped/null}, `value_mappings[]`, `summary` {created, skipped, partners_created} once committed, `error` |
| `setImportMapping` `PUT /imports/{id}/mapping` | `ImportMappingIn` {columns[] (merged), status_values[] and value_mappings[] (replace when sent; omit or null to keep)} | `ImportPreviewOut`; 409 once committing/committed; 422 for a bad header/status/value or two columns on one field, `fields[].loc` segmented (`["body", "value_mappings", 0, "value"]`) |
| `getImportPreview` `GET /imports/{id}/preview` | | `ImportPreviewOut` {counts {rows_total, ready, duplicates, already_imported, not_data, blocked}, problems[] {row_number, column, kind, severity, value, message}, unmapped[] {field, value, rows}, rows[] {row_number, action, legacy_ref, title, status, outcome, submitted_on, partner, problem_count}}. After commit: what commit did. |
| `commitImport` `POST /imports/{id}/commit` | {skip_rows_with_problems = true} | 202 `ImportJobOut`; poll `getImport` until committed/failed. Repeat-safe. 409 if a required column is unmapped, or rows have errors and skip is false. |

Suggested UI loop: show `unmapped` as the "map these values" step (status values → `status_values`; product,
channel, risk tier, partner, trigger terms → `value_mappings`), then `counts` + problems grouped by severity.

**Export.**

| Operation | Who | Request | Response |
|---|---|---|---|
| `createExport` `POST /exports` | reviewer, lead, admin | `ExportIn` {filters: ItemFilter, sort: ItemSort = newest, include_evidence_packs = false} | 202 `ExportOut`; 422 if packs requested for >200 approved items |
| `getExport` `GET /exports/{id}` | requester or admin (404 otherwise) | | `ExportOut` {kind, status pending/running/ready/failed, item_id, item_count, filename, download_url (when ready), error, created_at, finished_at} |
| `downloadExport` `GET /exports/{id}/download` | requester or admin | | the xlsx/zip (`Content-Disposition: attachment`); 409 until ready |
| `getEvidencePack` `GET /items/{id}/evidence-pack` | any role | | `EvidencePackOut` {item, approved_version, decision, findings, offer_terms, evidence, generated_at}; 409 never approved / legacy |
| `createEvidencePack` `POST /items/{id}/evidence-pack` | any role | | 202 `ExportOut` (kind evidence_pack); poll `getExport`. A marketer's pack lists partner-owned evidence (agreements) by hash only, per the ledger ruling. |

Job `error` strings are one line meant for the UI (the exception goes to the log).

xlsx columns: Item, Title, Status, Product, Channel, Partner, Risk tier, Round, Version, Markets, Tags,
Submitter, Reviewer, Open findings, Submitted, Approved, Approval expires, Legacy Request ID. Status labels are
`STATUS_META`'s (a test fails if `badges.tsx` changes without `exports/labels.py`). Legacy rows show the
tracker's submitter and reviewer.

## Verification

At the head of `wsG/import-export` after the review fix pass and a rebase onto `origin/main` (`efd4cc0`, which
brought in the LLM core, #23). Test DB suffix `wsG`; Postgres and Redis from compose.

```
$ uv lock --check && uv run pytest -q                 # backend/
1016 passed, 1 deselected in 17.56s
$ uv run --group lint ruff check .
All checks passed!
$ uv run --group lint ruff format --check .
228 files already formatted
$ uv run --group typecheck pyrefly check
 INFO 0 errors (132 suppressed, 1 warning not shown, use `--min-severity=warn` to see it)
$ manage.py makemigrations --check --dry-run
No changes detected
$ manage.py check --fail-level WARNING
System check identified no issues (0 silenced).
$ make schema; echo $?; git status --porcelain -- frontend/openapi frontend/src/api/generated | wc -l
0
0
$ npm run typecheck && npm run lint && npm run format:check && npm run test:run   # frontend/
All matched files use Prettier code style!
      Tests  145 passed (145)
$ make semgrep
Ran 273 rules on 564 files: 0 findings.
```

This branch removes 9 G contract-stub tests and adds 268 in imports/exports. The 1 deselected test is main's
opt-in live LLM eval. The oracle tests were mutation-checked: deleting the `"needs changes"` alias, or
disabling unique-prefix partner matching, fails 8 tests each.

**Live broker check at this head** (not just eager mode). A Celery worker from this worktree ran on a private
dev DB (`clearpath_wsg`, since dropped) and Redis DB 7, so the compose worker on DB 0, running main's code,
couldn't take the tasks.
- `create_sample_import` + `request_commit` → `imports.commit` on the worker: committed in 248 ms, created 178,
  skipped 2, 8 partners.
- `request_export(is_legacy=True)` → `exports.run`: ready in 74 ms, 178 rows, stored as
  `exports/2026/10/<uuid>.xlsx`.
- The worker logged start, outcome, and duration for each task. Autodiscovery lists `imports.commit` and
  `exports.run` in `app.tasks`.

## Deviations from the brief and contract, and why

- **Jobs are enqueued with `transaction.on_commit(task.delay)`, not via the outbox** (backend/CLAUDE.md says
  tasks are enqueued by the dispatcher). "Commit requested" and "export requested" aren't domain events, and the
  events that are (`IMPORT_COMMITTED`, `EXPORT_CREATED`) record results; adding request event types would mean
  editing `core.domain` and `audit.payloads`, which G doesn't own. Both tasks are idempotent on their job row.
  Cost: a lost enqueue (broker down at that instant) leaves an import `committing` (re-POST commit re-enqueues)
  or an export `pending` (request again).
- **Contract changes** (all through `make schema`): `commitImport` returns 202 `ImportJobOut` (was
  `ImportCommitOut`); `ImportMappingIn.columns` is optional and merged, `value_mappings` added; problems carry
  `severity`; `ImportTargetField` drops first_run/last_run/markets/asset_link/decided_on (no tracker column feeds
  them) and adds trigger_terms/version_number/rounds/approval/placement; new operations `listImports`,
  `downloadExport`, `createEvidencePack`; `ExportIn.sort`; `ExportOut.kind/item_id/filename/finished_at`;
  `EvidencePackOut.findings`. `getEvidencePack` stays JSON; the zip is a job, because it reads evidence files
  from storage (S3 in production) and can pass a few seconds.
- **Partners are created by the import service directly** (with `PARTNER_CREATED` events), not through
  `partners.services.create_partner`, which requires the Lead role; imports run as an admin. Unknown sheet
  `Type` defaults to affiliate.
- **Ref pattern is broader than the README's `^MCR-\d{2}-\d{3}$`**: any no-space token with a digit, so other
  trackers' IDs import. The sample's note row still fails it, and a ref-shaped cell on a row whose other required
  columns are all blank (a stray total) is a non-data row too.
- **`reviews/selectors.py` (E's file), one change**: `list_items`'s implicit queue (sort=queue, no status
  filter) excludes legacy items unless the caller sets `is_legacy`, matching `queue_stats`. Without it the 16
  open tracker rows (no version, nobody can review them) sit in every reviewer's queue. Test in
  `imports/tests/test_api.py::test_imported_open_items_stay_out_of_the_review_queue`.
- **Evidence pack is JSON on GET, zip on POST.** The brief has GET return the zip. Reading evidence files from
  storage can take more than a few seconds, so the zip is a job (`createEvidencePack` → `getExport` →
  `downloadExport`), and `getEvidencePack` keeps the contract's JSON record.
- **Values with no `ReviewItem` column** (trigger terms, approver, tracker version #, placement text and URLs)
  are written as lines in `notes` and kept in full on `ImportRow.parsed`. Legacy items get no `Placement` rows
  (`Placement.approved_version` is required).
- **`config/tests/test_contract.py`** (not G's file): removed G's eight stub entries and the upload-stub test.
  E edits the same `STUBS` list, so expect a trivial merge conflict.

## Risks and open questions

- **Legacy approvals have no `Decision`** (it requires a version). The item detail's `latest_decision` is null
  for an approved legacy item; the UI should show `approved_at` and the `ITEM_IMPORTED` timeline. Evidence packs
  for legacy items return 409 with that explanation.
- **Metrics (J)**: `LegacyTimeline` has first review, decision, and round count, not per-round dates. Per-round
  dates are in `ImportRow.parsed.segments` if "time per round" needs them for legacy history.
- **Cross-import ref reuse**: a later tracker that reuses a Request ID already imported from another file is
  skipped as `already_imported`, even if it's a different asset. Within one sheet the (title, date) rule
  applies; across files the `-b` suffix would need a rule for which suffix the newcomer gets.
- **Stuck jobs, remaining gap**: a soft time limit fails slow jobs visibly, and a crashed worker's redelivered
  message finishes the job (an export `running` past the hard limit is reclaimed; an import's rolled-back
  commit just runs again). If no redelivery happens, the UI shows `running`/`committing` until the user
  retries. Old export files are never deleted (no retention task yet).
- **Drift risks**: `exports/selectors.py` copies the queue sort keys and the implicit queue rule from
  `reviews.selectors` (private there). `EXPORT_CREATED`'s payload (audit's) has export id and count; filters
  and kind live on the job row the event points at.
- **Downloads stream through the app** (`FileResponse` over `storage.open`), not presigned S3 URLs. Fine for
  xlsx and packs at this scale; a very large bundled export holds a worker connection while it streams.
- **Upload parsing is in the request.** Bounded by 5 MB and the used-range check; a 5 MB workbook that is all
  real cells still takes openpyxl several seconds. defusedxml isn't installed (expat limits entity expansion).
- Commit holds one transaction for the whole sheet (≤5,000 rows). With the outbox's snapshot cursor that delays
  event dispatch by the commit's duration (0.24 s for the sample on a real worker).
- `config/tests/test_contract.py` and `reviews/selectors.py` are shared with E; expect small merge conflicts.
