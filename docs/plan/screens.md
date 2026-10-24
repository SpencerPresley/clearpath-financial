# Secondary screens + metrics (workstream J) Implementation Plan

> Issue #11. Report: `docs/plan/reports/screens.md` (the brief's path; the issue's `frontend-secondary.md` is
> superseded, as H2 did with the same conflict). UI review: `docs/plan/reviews/ui-screens.md`, screenshots in
> `docs/plan/reviews/ui/screens/`.
>
> **Execution:** three PRs on three branches, the last two built by subagents in their own worktrees in parallel
> with the first. The areas share no files except additive ones (`nav.ts`, an appended `theme.css` section each,
> `icons.ts` keys, `routeTree.gen.ts`), and each regenerates the API client with `make schema` (conflicts are
> resolved by re-running it, never by hand-merging generated files).

| PR | Branch | Scope | Base |
|---|---|---|---|
| 1 | `wsJ/screens` | Metrics backend (`backend/metrics/**`) + `/metrics` page | main |
| 2 | `wsJ/library-import` | `/library` (approved to run, precedent search, export, evidence pack) + `/import` | main |
| 3 | `wsJ/terms-partners` | `/terms` + `/partners`, `/partners/$id` | F's `wsF/offer-terms` until it merges, then main |

**Goal:** every remaining screen in product-spec "Screens" (except Outbox and the assistant, K's) works on real
data, with designed states, and the metrics are real numbers computed from the event log plus imported history.

## Global constraints

- Spec §5 is binding: color carries meaning (§5.2), icons only through `ui/icons.ts` (§5.2a), dense tables and
  stable layout with tabular figures (§5.3), domain copy (§5.4), empty/loading/error/partial states (§5.5), no
  LLM-styled UI (§5.6), React Aria for menus/comboboxes/popovers/dialogs (§5.7).
- `features/*` never import from each other; anything shared goes to `ui/` (additive). Routes are thin.
- Generated hooks only; never hand-edit `src/api/generated/**` or `openapi/ninja.json`. `make schema` after a
  backend change.
- `theme.css`: one appended section per area, no edits to existing rules; `app-*` classes for repeated utility
  combinations; no raw palette.
- Tests first: Vitest + MSW (opt into generated handlers per test; `src/test/server.ts` defaults stay core-only),
  e2e Playwright for one flow per screen, screenshots behind `SCREENSHOTS=1` in a per-area spec file
  (`e2e/screenshots-<area>.spec.ts`) writing to `docs/plan/reviews/ui/screens/<area>-<state>-<width>.png`.
- Backend: services write, selectors read and return dataclasses, `clock` injected, query-count test per list.
- Remove each screen's "Soon" tag by setting `to` on its `NAV_SECTIONS` entry when the screen lands.

## Metrics (PR 1)

### Definitions

Every measurement has a **start**, an **end**, and is attributed to the period containing its **end** (a
measurement exists once it completes). Native data comes from `audit.Event`; imported data from
`ITEM_IMPORTED.payload.timeline` (`LegacyTimeline`), never from the event's own `at` (import time). Legacy
timestamps are midnight UTC (day precision).

| Metric | Native start → end | Imported (LegacyTimeline) | Unit |
|---|---|---|---|
| Time to first review | item's first `ITEM_SUBMITTED` → its first `ITEM_REVIEW_STARTED` (E: the single first-review marker; fires on claim, first triage, or first decision) | `submitted_at → first_reviewed_at` (first reviewer comment) | hours |
| Time per round | each round start (`ITEM_SUBMITTED`, `ITEM_RESUBMITTED`, `ITEM_NEW_ROUND_STARTED`) → the next `DECISION_RECORDED` on the item before the next round start | not derivable: the timeline has endpoints and a round count, no per-round dates. Native only, labelled. | hours |
| Rounds per item | round starts since the previous terminal decision, counted at each terminal decision (`approved`, `approved_with_edits`, `rejected`; any lane except fast-track/reaffirm, which aren't rounds) | `timeline.rounds` when `outcome` is terminal, at `decided_at` | rounds |
| Time to fix live content | `ITEM_REOPENED` (approved → needs_rereview) → first approving `DECISION_RECORDED`, or the moment every takedown requested after the reopen is confirmed (`TAKEDOWN_CONFIRMED`), whichever is first (spec §4.2 ruling 6). Withdrawn with no placements: the withdrawal. | none (legacy items are never reopened) | hours |
| Throughput | `DECISION_RECORDED` (every outcome and lane: each is a completed review) | one per item with `decided_at` (the tracker dates only the final decision) | decisions |
| Items waiting > N days | snapshot now, not a period: queued statuses, `is_legacy=false`, `submitted_at < now − N days`, through `reviews.selectors.filter_items` so it equals the queue's `?waiting=N` view by construction (ledger stats-parity ruling) | excluded (ruling: legacy out of the queue) | items |

Open fix-live clocks (reopened, not resolved) are reported separately as a count with the oldest age, linking
to the queue's Needs re-review view.

### Contract

- `MetricsQuery` gains `partner_id: list[int]`. `MetricName` gains `throughput`; `aged_items` is summary-only.
- Every stat carries `native_count` and `imported_count` (the split is in the contract, not only the copy).
- `GET /metrics/summary` (`getMetricsSummary`), `GET /metrics/series` (`getMetricSeries`, week|month buckets,
  `period_start` per bucket, empty buckets included as count 0), new `GET /metrics/items` (`listMetricItems`):
  the measurements behind a stat or a bucket (item key/title/status/is_legacy, start, end, value, source), at most
  200, sorted by value descending. Every number on the page links to this list, computed by the same function
  that produced the number, so the list and the number can't disagree. Aged items link to the queue instead.
- Who: reviewer, lead, admin (marketers get 403). Nav shows Metrics to leads (product-spec Roles).
- Queries: constant in the number of items (native events in one query, imported events in one, aged counts in
  one aggregate); a query-count test grows the data between two measurements.

## Library + Import (PR 2)

- `/library`: two tabs as views: "Approved to run" (`GET /library?scope=approved_to_run`, default) and
  "Precedents" (`GET /library/search?mode=phrase|text&query=` + ItemFilter; hits show highlighted snippet parts,
  the matched version's outcome badge and the item's current status badge, ledger ruling). Filters: product,
  channel, partner, run-date range, approved range; in the URL. Export button: `POST /exports` with the view's
  ItemFilter + sort → poll `GET /exports/{id}` → `downloadExport`; optional evidence packs. Per item: evidence pack
  (`POST /items/{id}/evidence-pack` job → download); legacy items say why there's none (409 text) instead of a
  dead button.
- `/import` (admin): upload xlsx or "Load sample tracker" → column mapping → value mapping (`unmapped`) →
  problems preview grouped by severity → commit job with progress (poll) → summary with links to the imported
  items. Needs `item_id` on `ImportPreviewRowOut` after commit (additive field in `imports/`, G's app; flagged).

## Offer terms + Partners (PR 3)

- `/terms` (lead): current terms per product, version history, typed edit form per product (PL / CC; MTG has no
  rate terms, say so), impact preview before publish (F's `summary`, items, partners, lanes); Save disabled when
  the preview says nothing changed; publish; invalidate terms/items queries after.
- `/partners` (lead): list with counts; `/partners/$id`: details, agreement/evidence attachments (upload), items
  (`GET /items?partner_id=`, legacy included), findings history, repeat issues. Findings history needs a partner
  findings read (additive endpoint in `partners/`, flagged) unless an existing one covers it.

## Review focus

1. Metrics numbers equal their drill-down lists and the aged counts equal the queue views (parity tests).
2. Imported and native data are never mixed without a label.
3. Every control works against the real endpoint (no 501 controls ship, ledger ruling).
