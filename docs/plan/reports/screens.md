# Secondary screens + metrics (workstream J): report

Issue #11. Plan: `docs/plan/screens.md` (the brief's path; the issue's `frontend-secondary.md` is superseded, as H2
did with the same conflict). UI review: `docs/plan/reviews/ui-screens.md`, screenshots in
`docs/plan/reviews/ui/screens/`.

Execution: three PRs. Metrics (backend + page) built natively on `wsJ/screens`; Library + Import and Offer terms +
Partners built in parallel by two subagents in their own worktrees (`wsJ/library-import`, `wsJ/terms-partners`),
reviewed and merged by me. The areas share only additive files (`nav.ts`, appended `theme.css` sections, icon keys,
`routeTree.gen.ts`), and each regenerated the client with `make schema`.

## Metrics (PR 1)

### Definitions (what the numbers mean)

Each measurement has a start, an end, and a value, and belongs to the period containing its **end**. Native data
comes from `audit.Event`; imported data from `ITEM_IMPORTED.payload.timeline` (`LegacyTimeline`), never from the
import event's own time. All of it is in `backend/metrics/measures.py` as pure functions.

| Metric | Native start → end | Imported | 
|---|---|---|
| Time to first review | first `ITEM_SUBMITTED` → first `ITEM_REVIEW_STARTED` (E's marker: claim, first triage, or first decision) | `submitted_at → first_reviewed_at` (first reviewer comment, day precision) |
| Time per round | each round start (`ITEM_SUBMITTED`/`RESUBMITTED`/`NEW_ROUND_STARTED`) → the next `DECISION_RECORDED` | none: the tracker has no per-round dates |
| Rounds per item | round starts since the previous terminal decision, counted at each approve/approve-with-edits/reject that ends ≥1 round (so fast-track and reaffirm after a reopen aren't rounds) | `timeline.rounds` when the outcome is terminal |
| Time to fix live content | `ITEM_REOPENED` → first approving decision, or the moment every takedown requested after the reopen is confirmed (ruling 6). Reject/withdraw with nothing live ends it at once; request-changes doesn't end it | none: legacy items are never reopened |
| Throughput | every `DECISION_RECORDED` (all outcomes and lanes) | one per row with `decided_at` (the final decision only) |
| Items waiting > N days (3/7/14/30) | now, not a period: `filter_items` with the queue's own filter (queue statuses, non-legacy) | excluded |

Still-open fix-live clocks are reported separately ("1 re-review open · oldest 11.6 h") and listed by the drill-down,
which says why each is open ("Takedown unconfirmed" or "In re-review").

### API (`backend/metrics/`, tag `metrics`)

| Operation | What |
|---|---|
| `getMetricsSummary` `GET /metrics/summary` | Every stat with `native_count`/`imported_count` and each source's own median (durations) or mean (rounds); open fix-live; throughput per week; waiting counts; `imported_from`/`imported_to` (span of imported history under the filters) |
| `getMetricSeries` `GET /metrics/series?metric=&bucket=week|month` | One point per bucket, empty buckets included; `value` plus `native_value`/`imported_value`; `from_date`/`to_date` clipped to the period (the drill-down range for that bar) |
| `listMetricItems` `GET /metrics/items?metric=&open_only=` | The measurements behind a number, largest first, max 200, `total` = the number |

Query: `period_from`/`period_to` (default the 90 days ending today; backwards = 422 on `period_from`), `product[]`,
`channel[]`, `partner_id[]` (new), `include_legacy`. Readers: reviewer, lead, admin (403 for marketers; nav shows
Metrics to leads per product-spec Roles).

Queries are constant in the data size: native facts in one query, imported timelines in one, four waiting counts,
plus one item lookup for the drill-down. `test_query_count_does_not_grow_with_the_data` grows the data between two
measurements on four endpoints.

### Page (`/metrics`)

- Filter row: period presets (4 weeks, 13 weeks, 12 months; each starts on a Monday or the 1st, so only the current
  bucket is partial and it says "to date"), custom dates (a draft applied on Enter/Apply/blur; a backwards range is
  refused, never sent), product, channel, partner, "Include imported history" (URL `imported=false`). A provenance line states the imported span ("Imported tracker history covers Nov 3, 2025 – Oct
  23, 2026, at day precision") with "Show that period".
- Five tiles. When both sources contribute, a tile shows each source's own figure side by side ("5.0 h native ·
  14.0 d imported") and no blended headline; with one source it shows the figure plus p90 (from 5 measurements) or
  median. Every tile has the same four lines and opens the drill-down list (`aria-expanded`; closing returns focus).
  The fix-live tile adds a "1 re-review open · oldest 11.6 h" button for the running clocks.
- Waiting counts link to the queue with `waiting=N` and the same filters (equal by construction).
- Trend: metric switch, weekly/monthly, chart/table. Throughput stacks native and imported; durations and rounds are
  grouped bars per source; durations over two days chart in days. A bar or table row opens that bucket's items.
- Everything (period, filters, trend, drill-down) is in the URL. States: skeleton at the loaded height (provenance and
  waiting rows reserved), empty with "Clear filters" or a wider period, per-section error with Retry for server
  errors only (the trend keeps working when the summary fails; one Retry refetches all). The tooltip speaks the
  domain ("Week of Oct 5 · Imported median 14.0 d").

### Decisions made here (reversible)

- **Per-source figures instead of a blended number.** On the sample data, 58 imported first reviews (median 14 d)
  next to 40 native ones (5 h) blend into one median that moves with the mix, not with the team's speed, and hides
  the before/after the tool exists for. When both contribute, tiles and bars show each source and no blend; the API
  still returns the blended `median_hours`/`mean` for single-source use.
- **Open fix-live clocks are a drill-down, not a queue link** (plan said queue link). The queue's Needs re-review
  view can't include withdrawn items whose takedowns are pending, which ruling 6 counts as open; the list must equal
  the number.
- **Attribution by end time.** A round that started last week and ended today counts today. The alternative (start
  time) would make recent periods' numbers keep changing as open rounds finish.
- **Drill-down by same computation, not by `ItemFilter` links.** No `ItemFilter` reproduces "rounds that ended in
  week X", so the list comes from `GET /metrics/items` with the same function; it can't disagree with the number.
  Waiting counts are the exception: they are queue views, so they link to the queue.
- **Readers include reviewers.** Reversible in one `require_role`.

## Library + Import (PR 2)

Branch `wsJ/library-import`, stacked on `wsJ/screens` (PR #34). Built by a subagent in its own worktree; UI review
fixes in `reviews/ui-screens.md` (Library, Import).

### What's built

**Library (`/library`)**, for every role; Export only for reviewer, lead and admin (the server refuses marketers).
- *Approved to run*: `GET /library?scope=approved_to_run`, keyset pages of 50 with Load more. Title/key search,
  Product, Channel, Partner, Approved (date range), Placement running, Legacy chips; all state in the URL
  (`features/library/search.ts`, zod `validateSearch` with defaults stripped). Columns: item, title (+ Legacy
  badge), product, channel, partner, planned run, evidence pack. Fits 1280 without sideways scroll.
- *Precedents*: `GET /library/search?mode=phrase|text`, one hit per item: matched version, its outcome and date,
  the item's status now, and the snippet with matched words as `<mark>` text nodes (never HTML).
- *Export*: the approved view as xlsx, or a zip with an evidence pack per approved item (≤200). `POST /exports`,
  poll `GET /exports/{id}` every second, then a download link. The status shows on both tabs; Retry re-sends the
  failed request.
- *Evidence pack* per item (table and precedent hits): `POST /items/{id}/evidence-pack` → job → download. Legacy
  items say why there's none, in the server's own 409 sentence.

**Import (`/import`)**, admin only. Upload an xlsx or load the bundled sample → map columns (guesses pre-filled) →
map unknown values (status, partner, product…; 422s land on their row) → preview (counts; problems grouped by
severity with row, column, value, outcome) → commit (202, poll) → summary: created items with links, skipped rows
and warnings, a link to the approved legacy items. Recent imports list, polling while one commits. Steps before
commit stay one click away.

### Backend change

`ImportPreviewRowOut.item_id` (imports/, G's app): after commit each created row carries the item it became, read
in the same query as the rows (`values_list("parsed", "item")`; `django_assert_max_num_queries(3)` test). The
summary links every imported item without a second lookup. `make schema` regenerated `ninja.json` and the client.

### API gaps (not built here)

- **Approved and Expires columns (L6): follow-up.** Built before #32; #32 has since added
  `approval_expires_at` and `latest_decision` to `ItemRowOut`, so this is now UI-only. Adding a column breaks the
  1280 fit, so it needs a call on what gives way (Planned run is the candidate). On Precedents the date chip says
  "Item last approved" (it filters on the item's latest approval, not the hit's version).
- **Tracker IDs aren't searchable (L7).** `q` doesn't match `legacy_ref`, and `ItemRowOut` has no `legacy_ref`, so
  `MCR-26-045` can't be found from the library.
- **Precedent search has no paging.** `GET /library/search` takes `limit` only; the UI asks for 50 and says "Top 50
  precedents · narrow the filters" when it gets 50.
- **Downloads are plain links.** `api/mutator.ts` reads non-JSON bodies with `response.text()`, which corrupts xlsx
  and zip, so downloads are `<a href download>` from `ExportOut.download_url`, not a generated hook.
- **Partner names that exist only in the workbook.** The value step's partner options come from `GET /partners`. A
  tracker spelling of a partner the app doesn't have can be mapped to an existing partner or left for commit to
  create (8 created on the sample); nothing lists or pre-creates them from the mapping screen.
- **Stuck commit jobs (G's known gap).** A commit whose worker dies stays `committing` for ever: the UI keeps
  polling and nothing times it out or lets an admin retry. Seen in the real-backend check when Celery's prefork pool
  crashed on macOS (`--pool solo` worked).
- **Placement vs. planned run (L5).** The "Placement running" chip filters on Placement records; the "Planned run"
  column shows the submitter's intake dates. They can disagree, and the table has no placement column showing the
  filter's basis.

### Deviations

- **Export and pack jobs are page state, not sessionStorage** (the review offered either). Tab switches and
  filtering keep them; a reload loses the status line (the export still finishes server-side).
- **Product's extra width came from Channel** (7.5→7rem), not Partner or Evidence pack: the pack cell's Download
  link needs 7.5rem.
- **"Approved legacy items (n)"** counts this import's approved rows; the link shows every approved legacy item, so
  after a second, different import it lists more than n.
- **An import's finished badge is neutral, not success green** (green means approved, §5.2).

### Shared files touched

- `ui/layout/nav.ts`: `to` on Library and Import (kept alongside Metrics' entries in the rebase).
- `ui/layout/AppShell.test.tsx`: its "unbuilt section shows Soon" example used Library and now uses Outbox. **This
  collides with K's Outbox work**: when Outbox lands, that test needs another unbuilt section.
- `ui/FilterChip.tsx`: a copy of the queue's chip (features can't import features), with the `action.check` glyph.
  The queue keeps its own; folding the queue onto this one is a follow-up for the queue's owner.
- **Queue chip focus bug.** The queue's `.app-chip-btn` lost its focus ring the same way (L1). J's section adds
  `.app-chip-btn[data-focus-visible]`, a class rule, so it restores the queue chip's ring too; queue files weren't
  touched.
- `ui/badges.tsx`: `Badge` and `BadgeMeta` exported; `OUTCOME_META`/`OutcomeBadge` added. `ui/icons.ts`:
  `action.download`, `action.check`, `job.pending|running|done|failed`. New `ui/SnippetText.tsx`,
  `ui/DownloadLink.tsx`, `ui/search/params.ts`.
- `theme.css`: one appended "Library and Import" section, after Metrics'.

### Verified against the real backend (before the review fixes)

Private database, migrated and seeded, then dropped. Sample import: preview 178 ready, 1 duplicate, 1 not-data;
commit created 178, skipped 2, made 8 partners. `/library?legacy=only` loaded 50 + Load more. Export: 145 items, a
17 KB xlsx (`PK` magic). No API response ≥400. Not exercised live: upload, the values step, building an evidence
pack, precedent hits, export with packs, 422 paths, non-admin roles.

## Offer terms + Partners (PR 3)

Branch `wsJ/terms-partners`, stacked on `wsJ/library-import`. Built by a subagent in its own worktree; UI review
fixes in `reviews/ui-screens.md` (Offer terms, Partners). Both screens are lead-only in the nav.

### What's built

**Offer terms (`/terms`)**, product tabs in the URL (`?product=`). Mortgage prequalification gets a sentence (no
rate terms, spec §4.2 ruling 1).
- *In effect*: version, date, publisher, note, the values (credit card intro as "0% for 15 months"), and every
  version with what it changed against the one before.
- *Edit* (leads): a typed form per product, field | value in effect | new value, with per-kind validation (zod,
  mirroring `core.domain`'s ranges) and %/$ adornments. Edits debounce (300 ms) into
  `POST /terms/impact-preview`; the panel shows the server's summary, the outcome counts, the quoted fields that
  change, partners, and every affected item (live or not, quotes, what it becomes, lane, whether its numbers
  change).
- *Publish* is gated twice: the values must differ from the base (the backend refuses identical values), and the
  preview on screen must be for exactly these values on exactly this base. A confirm dialog repeats the counts and
  the changes. `based_on_terms_id` is the version the editor opened on; if another lead publishes first (a 409, or
  a refetch), the editor rebases: untouched fields take the new values, the lead's edits stay, and Publish waits
  for a fresh preview (T1).
- Unsaved edits lock the other product tabs; impact links open a new tab.

**Partners (`/partners`, `/partners/$partnerId`)**.
- *List*: name search (debounced) and status in the URL; type, status, items, approved, open findings, last
  submitted. Leads create partners inline (422s land on their fields, e.g. a duplicate name).
- *Detail*: facts (leads edit inline; PATCH sends only changed fields) and agreement and evidence (leads upload;
  agreements listed first). Tabs, each loading and failing on its own: Items (every status, Legacy marked),
  Findings history (keyset pages, narrowed to one rule by `?rule=`), Repeat issues (rule title linking to its
  findings).

### Backend endpoint(s) (`backend/partners/`, tag `partners`)

- `GET /api/partners/{id}/findings` (`listPartnerFindings`): every finding on any version of the partner's items,
  newest first (ties by id), keyset cursor on (`created_at`, id), `limit` (`PageLimit`, default 50), optional
  `rule_id`. Reviewers, leads and admins (`can_read_partner_attachments`; 403 otherwise), 404 for an unknown
  partner, 422 for a bad cursor. Fixed query count (`select_related`), tested with 2 rows and with 10.
- `RepeatIssueOut.rule_title`: the rule's title from the engine registry (`checks.engine.registry.RULES`) or the AI
  check's rules (`checks.llm.rules.LLM_RULES_BY_ID`); null for an id neither knows (retired, or imported history).
- `make schema` regenerated `ninja.json` and the client; no drift after the rebase onto `wsJ/library-import`.

### API gaps (not built here)

- **`normal_lane` isn't a subset of `will_need_rereview`.** `terms/impact.py` counts every affected item in the
  normal lane, expired and already-in-re-review included. The "of 9: n full review" line is computed client-side
  from items (approved, becoming Needs re-review, lane normal).
- **`already_in_rereview` counts all of them; only fast-track ones get new numbers.** The server's summary sentence
  counts the fast-track ones; the tile shows the total, with "n get new numbers" computed from items.
- **The impact preview takes no base.** It's always against the version in effect. That's right after a rebase (the
  base is then the version in effect), but nothing can ask for a preview "against v12".
- **Findings history has no total.** The tab shows the loaded count, with "+" when there are more pages.
- **Agreement visibility isn't in the response.** `PartnerDetailOut.attachments` is empty both for "none on file"
  and "you can't see them"; the page infers the second from the viewer's roles, duplicating the backend rule.
- **`last_submitted_at` includes legacy imports' tracker dates** (`Max(items__submitted_at)`), so a partner with
  only imported items shows the import's original date.
- **Findings history filters by rule only**, not state, severity or item (out of scope per the review).

### Deviations

- **T7 locks tabs instead of confirming.** The other product tabs are disabled with the reason beside them, rather
  than a confirm on switch: there's no dialog to dismiss, and the lead sees why before trying.
- **Three tiles, not the review's 2×2 grid** (T4/T8): Needs re-review (with the full-review split), Expire, In
  re-review now. "Already in re-review" became "In re-review now" so 1280 doesn't break "re-review".
- **The findings tab count runs the unfiltered history query on page load** (it shares the tab's cache entry): one
  extra request per detail view.
- **P11's "Imported only" never applies.** Every item has a `submitted_at`, so a null last-submitted means no items,
  and it shows "—".

### Shared files touched

- `ui/layout/nav.ts`: `to` on Offer terms and Partners (kept alongside Library, Metrics and Import in the rebase).
- `ui/labels.ts`: `PARTNER_TYPE_LABELS`, `PARTNER_STATUS_LABELS`, `FINDING_STATE_LABELS`.
- `ui/errorMessage.ts`: `isRetryable(error)` (5xx, or no status at all).
- `theme.css`: one appended "Offer terms + Partners" section, after Library and Import's.

### Decisions and follow-ups

- **P1: reviewers can't reach a partner page.** The nav entry is lead-only, and the review screen's Details tab
  shows the partner as plain text. These are two separate calls. (a) Whether Partners shows in reviewers' nav is a
  product decision for Spencer; the page already works read-only for reviewers (no Edit, no Upload). (b) Linking
  the partner name on the review Details tab is a small change for `features/review`'s owner. Neither was touched
  here.
- **`seen_versions` doesn't apply here.** These screens publish terms and preview impact; nothing here approves an
  item. Fast-track approvals go through the review screen (the single endpoint, with the version shown) and the
  queue's bulk bar (lead-only, `seen_versions` required since PR #33), so affected items reach approval through
  callers that already send it.

### Unverified

- **The outbox → Celery fan-out after publish.** The real-backend check published v2 and confirmed the history and
  diff, then ran `terms.fanout.fan_out_item` directly (items came back `reopened_fast_track` and `expired`). The
  `TERMS_PUBLISHED` outbox row → dispatcher → `terms.fan_out_item` task path wasn't run, so "items update within a
  few seconds" is the design, not something observed.
- **The review fixes weren't rerun against the real backend.** Unit tests (MSW) and the stubbed screenshots cover
  them; the rebase flow (T1) ran against a stubbed 409, not two real leads.

### Verified against the real backend (before the review fixes)

Private database, migrated and seeded, then dropped. Preview: "2 approved items quote v1; 1 will need re-review, 1
will expire."; publish v2 and its history diff; the unchanged gate. Partners list, detail, items, findings history,
upload, edit, create, and a duplicate-name 422 landing on Name.
