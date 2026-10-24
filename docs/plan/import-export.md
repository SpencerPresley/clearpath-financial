# Import, export, and evidence packs (workstream G) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (native). Steps use checkbox (`- [ ]`) syntax.
>
> **Execution: native, not subagent-driven.** Every import task leans on one set of types (`RawWorkbook`,
> `ImportMapping`, `ParsedRow`, `Problem`) and one oracle (`samples/README.md`); subagents would each re-read the
> oracle and drift on problem kinds and severities. Export and evidence packs share the job model and download
> path. One fresh reviewer over the whole branch before the PR supplies the independent read.

> **Deviations after review** (detail in `docs/plan/reviews/import-export.md`):
> - Upload cap 5 MB (not 10); reads bounded to the header's width, and a used range over 10,000 rows below the
>   header is refused.
> - `reviews/selectors.py` (E's): the implicit queue excludes legacy items, matching `queue_stats`.
> - `ImportMappingIn.status_values` / `value_mappings`: omitted or null keeps the saved list; two columns on one
>   field are refused.
> - Marketers' evidence packs list partner-owned evidence by hash only (ledger attachment ruling).
> - Tasks have `soft_time_limit=270`; a `running` export older than the hard limit is reclaimed.
> - Exported strings are always text (`data_type="s"`), illegal control characters stripped.

**Goal:** Admins migrate the legacy Excel tracker into legacy items (upload or "Load sample tracker", map
columns and values, preview problems, commit as a background job); reviewers export any filtered view to xlsx
and download a per-item evidence pack zip.

**Architecture:** `imports/workbook.py` reads the xlsx once with openpyxl into a typed, JSON-serializable
`RawWorkbook` stored on the job. `imports/normalize.py` is pure: `(RawWorkbook, ImportMapping, PartnerDirectory,
existing refs) -> NormalizedImport`, so preview and commit compute the same thing and the oracle is tested
without a database. Commit and every export run as Celery jobs with a status row; files go through Django's
storage API and are served only by authorized download endpoints.

**Tech Stack:** Django 6, django-ninja, Celery, openpyxl (runtime) + types-openpyxl (typecheck), pytest on
Postgres.

**Spec:** `docs/spec.md` §2, §4.2 ruling 7, §4.3 "Library, search, export" and "Import", §5.4, §6;
`samples/README.md` (the oracle); `docs/plan/reports/foundation.md` (Interfaces); `docs/plan/ledger.md`
(Rulings; >60 s work runs as a Celery job).

## Global Constraints

- Legacy items are metadata-only: `is_legacy=True`, `legacy_ref` kept, no `Version`, no `Decision`, owner null,
  `llm_check_status=skipped`. Outcome and dates go in `ITEM_IMPORTED`'s `LegacyTimeline`.
- Row problems are values (`Problem`), never exceptions (spec §6.1). Only an unreadable file raises
  (`InvalidInput` on field `file`).
- Status mapping is the README "Status values" table, case- and whitespace-insensitive; anything else is an
  `unmapped_status` error the admin maps. No guessing.
- Every string cell is stripped before matching or storing.
- Permissions: import = admin only (spec §1 Users table). Export = reviewer (lead implied) or admin. Evidence
  pack = any active user (every role reads every item today). Job status/download = its creator or an admin.
- **Job enqueue deviation:** services enqueue their own Celery task with `transaction.on_commit(...)` instead of
  via the outbox. Neither "commit requested" nor "export requested" is a domain event (the event types that
  exist record results: `IMPORT_COMMITTED`, `EXPORT_CREATED`), and `core.domain`/`audit.payloads` aren't G's.
  Tasks are idempotent on the job row (`select_for_update` + status check), so re-POSTing commit re-enqueues
  safely if a broker hiccup lost the first one.
- Celery task top level: `except Exception` → job `failed` with a one-line `error`, logged with job id and
  duration (spec §6.1, §6.4).
- Export labels match the UI (`frontend/src/ui/badges.tsx`): `In review`, `Changes requested`, `Re-review`, ...
- Sample workbook copied to `backend/imports/sample/clearpath_review_tracker.xlsx` (the Docker build context is
  `backend/`); a test compares cell values and hyperlink targets with `samples/` (bytes differ per regen).
- Endpoints: `operation_id` on every operation, `{int:id}` path params, return schema instances or lists.

## Review Focus

1. **Re-commit or a second import of the same file**: must create nothing new. Tests: commit twice; import the
   sample twice in two jobs (second preview shows 178 `already_imported`, commit creates 0).
2. **A non-xlsx or corrupt upload** (`b"PK..."`, a CSV renamed .xlsx): 422 on `file`, not 500. Test in API.
3. **An admin maps an unknown status/product value, then previews**: the row becomes ready. Test with a status
   `"On hold"` mapped to `submitted`.
4. **Evidence pack for a legacy or never-approved item**: 409 with a one-line message. Test both.
5. **A marketer downloads someone else's export by id**: 403/404. Test.

---

### Task 1: Dependencies, models, sample copy

**Files:** `backend/pyproject.toml`, `uv.lock`, `backend/imports/models.py`, `backend/exports/models.py`,
migrations, `backend/imports/sample/clearpath_review_tracker.xlsx`, `backend/imports/tests/test_sample_copy.py`.

**Produces:**
- `ImportJob(status, filename, file FileField("imports/%Y/%m/"), sheet_name, workbook JSON, column_mapping JSON
  {header: target}, status_mapping JSON [{source_value, status, outcome}], value_mapping JSON [{field, source_value,
  value}], created_by, created_at, updated_at, commit_requested_by null, commit_requested_at null, committed_at null,
  created_count, skipped_count, partners_created_count, error "")`.
- `ImportRow(job, row_number, legacy_ref null, action, item FK null, problems JSON, parsed JSON)`; unique
  `(job, row_number)`. Written at commit: the durable per-row record (trigger terms, approver, version #).
- `ExportJob(kind items_xlsx|evidence_pack, status, filters JSON, sort, include_evidence_packs, item FK null,
  created_by, file FileField("exports/%Y/%m/", blank), filename, item_count null, error, created_at, started_at,
  finished_at)`.
- No `choices=` on fields (`core/tests/test_model_conventions.py`).

- [ ] Add `openpyxl>=3.1.5` to dependencies, `types-openpyxl` to typecheck; `uv lock`.
- [ ] Test `test_bundled_sample_matches_samples_dir`: for every sheet, `(coordinate, value, hyperlink target)`
      equal; skipped if `../samples` is absent (prod image).
- [ ] Models + `makemigrations imports exports`; `makemigrations --check` clean. Commit.

### Task 2: Workbook reader (pure)

**Files:** `backend/imports/workbook.py`, `backend/imports/tests/test_workbook.py`.

**Produces:** pydantic frozen models `RawCell(value: str | datetime | float | int | bool | None, hyperlink: str |
None)`, `RawRow(row_number: int, cells: tuple[RawCell, ...])`, `RawSheet(name, header_row: int, headers:
tuple[str, ...], rows: tuple[RawRow, ...])`, `PartnerSheetRow(name, type, description, contact_email,
agreement_date: date | None, status, notes)`, `RawWorkbook(tracker: RawSheet, partners: tuple[PartnerSheetRow,
...], reviewers: tuple[str, ...])`; `read_workbook(source: IO[bytes]) -> RawWorkbook`; `UnreadableWorkbook(ValueError)`.

- Load with `openpyxl.load_workbook(source, data_only=True)` (not read-only: read-only drops hyperlinks).
  Naive datetimes → UTC. Strings stripped; `""` → None. Tracker sheet = the sheet whose header row maps the most
  target fields via `guess_column_mapping` (Task 3); header row = first of the first 10 rows with ≥ 3 text cells.
  Partners sheet: headers include "partner name" and "type". Reviewers: the `Lists` column headed "Reviewer".
  Limits: 10 MB, 5,000 data rows → `UnreadableWorkbook` with a one-line reason.
- [ ] Tests on the sample: 180 rows (r2..r181), 17 headers, r34 asset hyperlink target, r19 note text in column A,
      8 partners with `CardPerks Weekly` type `Affiliate`, reviewers include `Nikhil Rao`; `b"PK..."` raises
      `UnreadableWorkbook`. Implement; pass; commit.

### Task 3: Mapping and normalization (pure, the oracle)

**Files:** `backend/imports/mapping.py`, `backend/imports/normalize.py`, `backend/imports/schemas.py` (enums),
`backend/imports/tests/test_mapping.py`, `backend/imports/tests/test_normalize.py`, `backend/imports/tests/oracle.py`.

**Produces:**
- `ImportTargetField`: legacy_ref, submitted_on, submitter, product, channel, title, partner, risk_tier,
  trigger_terms, reviewer, version_number, rounds, status, comments, approval, expires_on, placement, notes,
  ignore. Required: legacy_ref, submitted_on, title, product, channel, status.
- `guess_column_mapping(headers) -> dict[str, ImportTargetField]` by keywords on the casefolded header.
- `DEFAULT_STATUS_MAP` (README "Status values"), product/channel/risk/Y-N maps, `normalize_key(s)` (casefold,
  drop non-alphanumerics), `status_key(s)` (casefold, collapse whitespace).
- `ImportMapping(columns, statuses, values)`, `PartnerDirectory(entries: tuple[(key, canonical name)])` built
  from sheet partners + existing DB partners, `resolve_partner(raw) -> (name | None, fuzzy: bool)`: exact key,
  then unique prefix.
- `Severity` (error|warning|info), `ImportProblemKind` (missing_mapping, missing_value, unparseable_date,
  coerced_date, unmapped_status, inferred_status, unknown_value, unknown_partner, fuzzy_partner, missing_expiry,
  unknown_trigger_terms, derived_approval_date, unresolved_approver, inconsistent_dates, duplicate_row,
  reused_ref, already_imported, not_data_row), `RowAction` (create, skip_duplicate, skip_already_imported,
  skip_not_data, blocked).
- `ParsedRow(row_number, legacy_ref, source_ref, title, asset_url, submitter, product, channel, partner_name,
  risk_tier, trigger_terms: bool | None, reviewer, version_number, rounds, status, outcome, comments, segments:
  tuple[CommentSegment], approver, approved_on, approval_derived, expires_on, placement, placement_urls, notes,
  timeline: LegacyTimeline, action, problems)`; `NormalizedImport(rows, problems (job-level), unmapped:
  tuple[UnmappedValue(field, value, count)], counts)`.
- `normalize(workbook, mapping, directory, existing_refs: frozenset[str]) -> NormalizedImport`.

Rules beyond the README text: dates accept datetime, `M/D/YY`, `M/D/YYYY`, ISO, `Mon D` (year from `MCR-YY-`);
comment segments by the README regex, year from submission year, +1 each time the month goes backwards (first
segment vs. submission month); approval cell `M/D/YY - F. Last` or `F. Last` (date from last segment, warning);
approver resolved by first initial + last name against reviewers; decided_at for approved/rejected = approval
date or last segment, for changes_requested = last segment, none for open statuses; first_reviewed_at = first
segment; rounds = Revision Round; `LegacyTimeline` ValidationError → `inconsistent_dates` error; duplicate = same
ref and same (title, submitted_on) → `duplicate_row`, skip; same ref otherwise → `-b`, `-c`… in sheet order with
a `reused_ref` warning; ref in `existing_refs` → `already_imported`, skip. Risk tier from the sheet when mapped,
else `derive_risk_tier`. Partner unknown → error. Product/channel unknown → error; risk/Y-N unknown → warning;
all unknowns listed in `unmapped`.

- [ ] `oracle.py`: the README's tables as Python data (status 27 rows, product 34, dates 15+3, approver-only 6,
      blank expiry 6, whitespace 9, partner 4, Y/N 13, totals).
- [ ] Parametrized tests per README section asserting the `ParsedRow` field and the problem kind+severity;
      exhaustive "Every raw value, mapped" tests for status/product/Y-N/partner; totals: 180 rows, 178 create,
      177 distinct source refs, 1 duplicate (r68), 1 not-data (r19), 0 blocked; status counts 132/13/11/8/6/8;
      open on 2026-10-23 = 16, unassigned 8; submitted range 2025-11-03..2026-10-20; MCR-26-101 r122 →
      `MCR-26-101-b`; cross-New-Year rows have comment years 2026; unknown status "On hold" → error, then mapped.
- [ ] Implement; pass; commit.

### Task 4: Import services, selectors, commit task

**Files:** `backend/imports/services.py`, `selectors.py`, `tasks.py`, `tests/test_services.py`.

**Produces:**
- `create_import(*, actor, filename, source: IO[bytes], clock) -> int`; `create_sample_import(*, actor, clock)
  -> int`; `set_mapping(*, actor, job_id, mapping: ImportMapping, clock) -> None` (validates targets, required
  fields, value types; `Conflict` once committing/committed); `request_commit(*, actor, job_id,
  skip_blocked: bool, clock) -> None` (`Conflict` if blocked rows exist and `skip_blocked` is false; no-op once
  committed; enqueues `imports.commit` on commit); `commit_import(*, job_id, clock) -> None` (task body).
- `get_import(*, viewer, job_id) -> ImportJobRow`; `get_preview(*, viewer, job_id) -> ImportPreview`;
  `list_imports(*, viewer) -> tuple[ImportJobRow, ...]`.

Commit, in one transaction: `select_for_update` the job; return if committed; `pg_advisory_xact_lock` on a
fixed key so concurrent jobs serialize; recompute `normalize` with live existing refs; create missing sheet
partners (`PARTNER_CREATED` each; not via `create_partner`, which needs Lead); create items; `ITEM_IMPORTED` per
item (`to_status`, timeline); `ImportRow` per sheet row; `IMPORT_COMMITTED`; counts. On exception: rollback,
then mark `failed` in a new transaction.

- [ ] Tests: sample commit totals match README exactly (178 items, statuses, outcomes from event payloads,
      legacy_ref set, MCR-26-101-b, 8 partners, LegacyTimeline round-trips through `parse_payload`); re-commit is a
      no-op; second job creates 0; non-admin `NotPermitted`; mapping change after commit `Conflict`; approved
      item fields (`approved_at`, `approval_expires_at`, null for blank expiry rows); task failure marks failed.
- [ ] Implement; pass; commit.

### Task 5: Import API

**Files:** `backend/imports/api.py`, `schemas.py`, `tests/test_api.py`, `config/tests/test_contract.py`
(remove G stubs), `config/tests/test_query_counts.py` (add `listImports`).

Endpoints: `POST /imports` (201 ImportJobOut), `POST /imports/sample` (201), `GET /imports` (list),
`GET /imports/{id}`, `PUT /imports/{id}/mapping` (200 ImportPreviewOut), `GET /imports/{id}/preview`,
`POST /imports/{id}/commit` (202 ImportJobOut; poll `getImport`).

- [ ] API tests: full flow on the sample through the client with on-commit callbacks executed; bad file 422;
      marketer 403. Implement; pass; commit.

### Task 6: Exports and evidence packs

**Files:** `backend/exports/labels.py`, `xlsx.py`, `evidence.py`, `services.py`, `selectors.py`, `tasks.py`,
`api.py`, `schemas.py`, `tests/…`.

**Produces:**
- `request_export(*, actor, filters: ItemFilter, sort: ItemSort, include_evidence_packs, clock) -> int`;
  `request_evidence_pack(*, actor, item_id, clock) -> int` (`Conflict` if no approving decision; legacy message
  distinct); `run_export(*, job_id, clock) -> None` (task body; records `EXPORT_CREATED`).
- `evidence.latest_approval(item_id) -> Decision`; `evidence_pack(item_id) -> EvidencePack` (selector; the JSON
  summary endpoint) and `write_evidence_pack(pack, zf, prefix)`: `summary.txt`, `approved-version-vN.txt`,
  `decision.json` (incl. findings on the approved version with triage), `offer-terms/<product>-vN.json`,
  `evidence/<attachment-id>-<name>`, `history.json`, `manifest.json`, `SHA256SUMS` (`sha256sum -c` format).
  Evidence manifest records the decision-time hash and the current file hash and flags a mismatch.
- xlsx headers: Item, Title, Status, Product, Channel, Partner, Risk tier, Round, Version, Markets, Tags, Owner,
  Assignee, Open findings, Submitted, Approved, Approval expires, Legacy ref. Datetimes written naive UTC with a
  date format.
- Endpoints: `POST /exports` (202 ExportOut), `GET /exports/{id}`, `GET /exports/{id}/download` (FileResponse),
  `GET /items/{id}/evidence-pack` (EvidencePackOut JSON), `POST /items/{id}/evidence-pack` (202 ExportOut).
  `include_evidence_packs` → a zip with `items.xlsx` + `evidence-packs/CP-n/…` for items with an approval; over
  200 such items → `InvalidInput`.

- [ ] Tests: xlsx headers and labels read back with openpyxl; filters honored with the creator as viewer
      (`mine`); evidence zip contents and SHA256SUMS verify; mismatch flagged; legacy/never-approved 409;
      marketer can't export (403) but can fetch a pack; other user's export 404; `EXPORT_CREATED` recorded.
- [ ] Implement; pass; commit.

### Task 7: Schema, checks, review, report

- [ ] `cd frontend && npm ci`; `make schema`; commit `frontend/openapi/ninja.json` + `frontend/src/api/generated`.
- [ ] ruff check/format, pyrefly, `makemigrations --check`, `manage.py check --fail-level WARNING`, pytest.
- [ ] Fresh reviewer → `docs/plan/reviews/import-export.md` with resolutions; fix.
- [ ] Report `docs/plan/reports/import-export.md`; PR "Import, export, and evidence packs" (Closes #8).
