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
