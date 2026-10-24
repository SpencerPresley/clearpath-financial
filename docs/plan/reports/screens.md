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
