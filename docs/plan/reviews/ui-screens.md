# UI review: secondary screens (workstream J, #11)

Each area was reviewed by a fresh reviewer subagent that had not seen the build. The reviewer read spec §5,
§4.3, the product spec screens, the ledger rulings and the `make-interfaces-feel-better` skill, then
looked at every screenshot at 1440×900 and 1280×800. The metrics reviewer also drove the page live,
against a private database seeded with the sample tracker (178 imported items) and about 46 native items
created through the services.

Screenshots are in `ui/screens/`:
- `metrics-<state>-<width>.png` are stubbed API states (Playwright `page.route`; `frontend/e2e/screenshots-metrics.spec.ts`).
- `metrics-real-*` were captured against the real backend after the fixes.

## Metrics (`/metrics`)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| M1 | blocker | The custom dates were controlled straight from the URL. Every keystroke round-tripped through the router, which reset Chrome's date-segment typing ("03-15" became 03-01, 03-15, 03-02, 03-26) and pushed a history entry per key. | Fixed. `CustomRange` keeps a local draft and applies it on Enter, Apply, or leaving the fields, with `replace: true`. Checked live: typing `03152026` gives `2026-03-15`, the URL changes only on Enter, and no history entries are added. |
| M2 | should-fix | Layout shifted when data arrived. The provenance line and waiting row rendered only with data (the trend moved about 116px), and the open re-review pill sat outside the tile's minimum height. | Fixed. The provenance row is always rendered with `min-h-7`, and the waiting row renders skeleton chips while loading. The minimum height (`min-h-42`) moved from the button to the tile, so it includes the pill. The error box uses the same height. |
| M3 | should-fix | Partial buckets weren't marked. "13 weeks" drew 14 bars, the first covering one day. | Fixed. Presets start on a bucket boundary (4w/13w on a Monday, 12m on the 1st), so only the current bucket is partial. Partial buckets say "(to date)", or which dates they cover, in the table and tooltip (`isPartial`). |
| M4 | should-fix | The default tooltip showed `x Oct 2026 / y 0.229`: raw field names and a unitless value in days. | Fixed. A custom `renderTooltipBody` reads like "Week of Oct 5 / Imported median 14.0 d" or "4 imported decisions". With a custom body the chart applies no chrome (`customTooltipCardStyle` in `@tanstack/charts/dist/tooltip.js` is transparent), so `.app-metric-tooltip` is the overlay surface. |
| M5 | should-fix | Range labels dropped the year ("Throughput · Oct 25 – Oct 24"). | Fixed. `rangeLabel` adds years when a range crosses a year or isn't in the current year. |
| M6 | should-fix | When both sources contributed, the tile led with a blended median. That number moves with the native/imported mix, not with how fast the team works. | Fixed. Tiles show the native and imported figures side by side at equal weight ("5.0 h native · 14.0 d imported"). A single figure with p90 appears only when one source contributes. |
| M7 | should-fix | The open re-review pill was 20px tall, carried meaning by colour alone, and said "open now". | Fixed. It is at least 28px tall, has the `status.needs_rereview` glyph, and reads "1 re-review open · oldest 11.6 h". It wraps inside the button at 1280. |
| M8 | should-fix | An open fix-live row showed "Withdrawn … Ended: Open", which reads as a bug. | Fixed. Open rows say why the clock is still running: "Takedown unconfirmed" (withdrawn or rejected, takedowns not yet confirmed, per ruling 6) or "In re-review". The plan said this count would link to the queue's Needs re-review view. It stays a drill-down, because that queue view can't show withdrawn items whose takedowns are pending, and the list must equal the number. Recorded as a plan deviation. |
| M9 | should-fix | Closing the list dropped focus to `BODY`. Tiles showed their state only visually. | Fixed. Tiles and the pill carry `aria-expanded`, plus `aria-controls` while open. Closing returns focus to the trigger. Opening moves focus to the list heading, but only when the user opened it; a URL that loads with the list open leaves focus alone (tested). |
| M10 | should-fix | A backwards custom period was sent, returned 422 after retries, and offered a Retry that could never succeed. | Fixed. The form refuses it ("Ends before it starts.", Apply disabled). A hand-edited backwards URL is never sent (`enabled: ordered`) and says why. Retry appears only for server errors (`isServerError`). |
| M11 | should-fix | The partial state's header said "temporarily unavailable" above working metrics. A full outage showed two messages and two Retry buttons. | Fixed. The header copy is "Couldn't load the headline numbers.", and the trend stays quiet when the summary already reports the outage. One Retry refetches every metrics query. |
| M12 | should-fix | The empty state was duplicated by an empty 240px trend, and it offered only "Last 12 months" even when a filter caused the empty result. | Fixed. The trend is hidden when there's nothing to show. When filters are set, the action is "Clear filters" and the copy says "for these filters". |
| M13 | should-fix | Chart bars aren't keyboard-reachable on their own. | Declined. The Table view lists the same buckets, and each row's button opens that bucket's items. That is the accessible path, and it's one click on the view switch. |
| M14 | should-fix | The drill-down sat between the tiles and the trend, pushing the chart down when it opened. | Fixed. It renders below the trend and scrolls into view (`block: 'nearest'`) when opened. |
| M15 | nit | With imported history excluded, the caption still described imported data. | Fixed. `importedNote` is hidden when imported history is excluded, and the provenance row says "Native data only". |
| M16 | nit | Choosing Custom reflows the header. | Declined. The shift is user-triggered, not a load shift under §5.3. |
| M17 | nit | Tile lines didn't line up across tiles, and a lone "·" wrapped at 1280. | Fixed. Every tile has the same four lines (label, figure, how it's computed, counts by source). Count segments are unbreakable spans. |
| M18 | nit | p90 was shown for 1–2 measurements, where it is just the maximum. | Fixed. p90 is hidden below 5 measurements (`P90_MIN`). |
| M19 | nit | The UI says imported, the URL said `legacy`. | Partly fixed. The URL parameter is now `imported`. The API (`include_legacy`, `is_legacy`, `legacy_ref`) is shared with the import, queue and library code, so renaming it belongs to its owners. |
| M20 | nit | "has no reviews completed" next to "decisions" everywhere else. | Fixed. It now reads "has no decisions". |
| M21 | nit | The empty-state action was `false` on 12 months, which rendered an empty action row. | Fixed. It is now `undefined`. |
| M22 | nit | Shell-level items: "Search (soon)" and the "Soon" tags on other sections. | Inherited and project-wide. J's tags are removed as each screen lands. |
| M23 | nit | Truncated titles had no full text, and the Source column repeated "native only" on every row. | Fixed. Titles have a `title` attribute, and the Source column appears only when both sources contribute. |
| M24 | nit | The inner radius on the end tiles matched the outer radius. | Fixed. It is now `calc(var(--radius-lg) - 1px)`, concentric with the 1px border. |

Found after the fixes, in the recaptured real-data screenshots, and fixed:
- The re-review pill text overflowed a fixed `h-7` at 1280, so it now uses `min-h-7` and wraps.
- The drill heading stole focus on page load.
- "Takedown unconfirmed" wrapped in a 7rem column, which is now 10rem.
- The custom tooltip had no surface.

## Library (`/library`)

Screenshots: `library-<state>-<width>.png` and `import-<state>-<width>.png`, stubbed API states (`frontend/e2e/screenshots-library-import.spec.ts`), recaptured after the fixes. The review marked each finding FIX, PARTIAL or DEFER and flagged L1 and I1 as blockers; the other severities are the builder's.

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| L1 | blocker | `.app-chip-btn` sets `outline-style:none` in `@layer components`, so the global `[data-focus-visible]` ring in `@layer base` loses and tabbing through the chips shows nothing. | Fixed. `.app-chip-btn[data-focus-visible]` gets a 2px `--color-focus` outline inset by 2px, in J's theme section. The queue's own chip has the same bug; queue files untouched, reported to the J owner. |
| L2 | should-fix | The export job id lived in `useState` inside `ExportControl`, which mounts only on the approved tab. Switching to Precedents and back lost "Building…" and the download. A row's pack state was lost the same way when a filter removed the row. | Fixed. `exportJobs.tsx` holds one record per key (`export`, `pack:<id>`) in a provider above `<Tabs>`. The mutation's own `onMutate`/`onSuccess`/`onError` write the record, so a control that unmounts mid-request still lands its job. `ExportStatus` renders on both tabs; the Export menu stays approved-only. Page state, not sessionStorage: a reload loses the job. Tests: tab switch keeps running → download; a row filtered away and back keeps its pack link. |
| L3 | should-fix | The Legacy chip on Precedents: search covers only ever-approved versions and legacy items have none, so "Only" is always empty and "Exclude" does nothing. | Fixed. The chip is hidden on Precedents, `toSearchParams` never sends `is_legacy`, and `hasFilters` ignores the legacy choice there (a stale `legacy=only` in the URL can't show "Clear filters"). Tested. |
| L4 | should-fix | The pack button sat in the "Matched v1 · Approved" row, reading as v1's pack, but the backend packs the item's latest approving decision. | Fixed. It sits in the head row after "Now [status]", labelled "Build item pack". |
| L5 | should-fix | The "Running" chip filters on Placement dates while the column shows the intake planned run. | Renamed to "Placement running"; the column stays "Planned run". The two still measure different things (placements vs. the submitter's planned dates); that mismatch is recorded in the report. |
| L6 | should-fix | On Precedents the Approved chip filters on the item's latest `approved_at`, not the matched version's date. Approved and Expires columns are missing. | Partly fixed. On Precedents the chip reads "Item last approved" with that description. Columns: after #32 added `approval_expires_at`, the orchestrator ruled that "Expires" replaces "Planned run" on Approved to run (PR 3). An approval with no expiry, as on legacy imports, reads "No expiry". This also removes L5's planned-run/placement mismatch from the table. |
| L7 | should-fix | `q` doesn't match `legacy_ref`, and `ItemRowOut` has no `legacy_ref`, so `MCR-26-045` can't be found. | Deferred: backend work in reviews/. Recorded as an API gap. |
| L8 | should-fix | Label in Name: visible "Build pack", accessible name "Evidence pack for CP-1088". | Fixed. The accessible name is the visible label plus the key: "Build pack for CP-1088" in the table, "Build item pack for CP-1088" on a precedent. |
| L9 | should-fix | Layout shift at 1280: with chips set, "Clear filters" wrapped and dropped the table 34px; Phrase→Text wrapped the long hint and dropped results 20px. | Fixed. The filter row is `flex-nowrap`; empty chips keep their labels, set chips shrink (`max-w-56 min-w-24`, truncating), and "Clear filters" is `ml-auto shrink-0` at the row's end. The mode hint has its own `h-4` truncating line under the search box in both modes. |
| L10 | should-fix | Product (7.5rem) truncated "Mortgage preq…"; title links had no full text. | Fixed with a deviation: Product is 8.5rem, but the rem came from Channel (7.5→7rem; "Affiliate page" still fits), not Partner or Evidence pack, because the pack cell's "Download" link needs 7.5rem. "Mortgage prequalification" still truncates at 8.5rem, so the cell keeps its `title`. Title links (table and precedents) carry `title`. Total fixed width unchanged (46.5rem), so 1280 doesn't scroll sideways. |
| L11 | should-fix | Precedent skeleton 93px per hit against 121px real. | Fixed. The skeleton has the head row with the pack slot, two 20px snippet lines and a badge-height meta row: 121px per hit, measured on the recaptured screenshot. |
| L12 | nit | The chip read "Legacy: Exclude legacy". | Fixed. Options are "Excluded" and "Only". |
| L13 | nit | `title` on the non-focusable Legacy badge. | Fixed. Removed. |
| L14 | nit | Three names for one view: "Precedents", "Search past approvals", "Search approved copy". | Fixed. The field is "Search precedents"; the idle state is "Search precedents" and defines a precedent. |
| L15 | should-fix | "Retry export" re-ran with the current filters. | Fixed. The store keeps the failed request body (`ExportIn`) and Retry re-sends it. Tested: export with Email, change the filter to SMS, Retry posts the Email body. |
| L16 | nit | The FilterChip check mark used `action.approve`, the decision glyph. | Fixed. New `action.check` key (CheckFat, bold), used in `ui/FilterChip.tsx` only. |
| L17 | nit | (taste) | Left as is, as asked. |

## Import (`/import`)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| I1 | blocker | Same lost focus ring on `.app-import-steps-btn`. | Fixed with the same rule (one selector list with L1's). |
| I2 | should-fix | The Warnings header said "Imported with a note", but the backend files skipped rows (duplicate, not-a-data-row, already-imported) as warnings and info. | Fixed. Group effect text is gone. Problem tables have an Outcome column, Imported or Skipped, from `preview.rows[].action` by `row_number`; "—" for sheet-level problems. Tested on the Info group (row 19 → Skipped). |
| I3 | should-fix | Import status badges were label-only, and "Imported" used approval green. | Fixed. They go through the shared `Badge` (now exported from `ui/badges.tsx`) with new `job.*` glyphs: Uploaded/Mapped neutral with a dashed circle, Importing info with an hourglass, Imported neutral with a checked square, Failed error with a crossed square. |
| I4 | should-fix | After commit the summary showed only created rows; the post-commit warnings vanished. | Fixed. Below the items table, collapsed: "Skipped (n)" (row, Request ID, title, why) and "Warnings (n)" (the problem table with outcomes). Tested both collapsed and the skipped reasons. |
| I5 | should-fix | "Open in library" lands on Approved to run with legacy=only: 145 of 178 items. | Fixed. "Approved legacy items (n)", n = created rows whose status is approved (the approved view's scope is current status approved, `reviews/selectors.py` `LibraryScope.APPROVED_TO_RUN`). Hidden when n is 0. Caveat: the link shows every approved legacy item, so after two different imports it lists more than this import's n. |
| I6 | should-fix | Recent imports didn't poll. | Fixed. `refetchInterval` 2s while any row is committing, off otherwise. Tested: a committing row turns into its result, then polling stops. |
| I7 | should-fix | The error copy says "map it or the row is skipped", but the only route to Values was the step list, and clickable steps looked like the others. | Fixed. "Map N values" (secondary) sits next to the import button while `preview.unmapped` is non-empty and goes to the Values step (tested). Pickable steps are primary text and underline on hover. |
| I8 | nit | "Importing 178 rows…". | Fixed. "Importing 178 items…". |
| I9 | nit | Done steps showed a number. | Fixed. A check glyph, plus sr-only "Done:". |
| I10 | nit | Severity group headers had no glyph. | Fixed. feedback.error, severity.warning, feedback.info, tinted by severity. |
| I11 | should-fix | Problem messages truncated. | Fixed. The message cell wraps (`whitespace-normal`, `text-wrap: pretty`). |
| I12 | should-fix | "Save and continue" sat below the fold with 18 columns. | Fixed. The columns step's actions are a sticky footer at the bottom of the scrolling main. |
| I13 | nit | "with the usual mess" and a hard-coded 180. | Fixed. "The team's 2025–26 review tracker, with the tracker's known inconsistencies." No count (no API returns it before loading). |
| I14 | should-fix (orchestrator) | `import-preview-errors` showed "4 Blocked by errors" and "4 rows with errors are skipped" above an Errors table listing 2 rows. | Fixed. The cause was the fixture: its counts were typed by hand (`blocked: 4`) next to 2 error problems. The backend cannot produce this: a row is BLOCKED exactly when it has an ERROR problem (`normalize.py` `_action`), and the preview returns every row's problems. `test_preview_blocked_count_equals_the_rows_its_errors_name` checks this with 3 errors on 2 rows. The fixture now derives `blocked` from its own error rows (6 errors on 5 rows, matching its unmapped-value counts). The group header names rows when a row has more than one problem ("Errors · 6 in 5 rows"), so it agrees with "5 rows with errors are skipped"; a test checks that the listed row numbers equal `blocked`. |

Found while recapturing, and fixed: the shrinking filter row first truncated empty chips ("Prod…"); only set chips shrink now. The pack column's "Download" link overflowed 7rem.

## Offer terms (`/terms`)

The review marked T1 a blocker and the rest FIX or DEFER without a level; the levels below other than T1's are
mine. T1, T2, T3 and T7 each got a test that failed before the fix (`TermsPage.test.tsx`, tagged with the id).

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| T1 | blocker | `based_on_terms_id` came from the live `current` prop. After a 409 (or a focus refetch) the base moved to v13 while untouched fields kept v12's values, so v14 would silently undo the other lead's change. | Fixed. The base is frozen when the editor opens (`useFrozenBase`). When a newer version lands, fields the lead didn't change take its values, their edits stay, the 409 line gives way to "v13 was published since you opened this (Sam Okafor)…", and the preview query is keyed on the base id, so Publish waits for a fresh preview. Tested: 409, refetch to v13 (APR max 29.99), APR max resets, APR min keeps 12.99, Publish v14 sends `based_on_terms_id: 113` with v13's APR max. |
| T2 | should-fix | APR min 40 over max 35.99 showed no error; the gate said "Complete the fields…". | Fixed. min > max puts an error on both fields, so it shows on the one just edited; the gate says "Fix the highlighted fields to preview the impact." when values are filled but invalid. |
| T3 | should-fix | A cleared or invalid field unmounted the preview and affected items. | Fixed. Both stay, faded, with `aria-busy`; they're hidden only when the values equal the base. |
| T4 | should-fix | Lane shown on expired rows; four equal tiles read as 15 items. | Fixed. Lane is "—" unless the row will be Needs re-review. Three tiles (Needs re-review, Expire, In re-review now), each with a detail line; the full-review split is under re-review ("of 9: 1 full review" / "all fast-track"), computed from approved items only (see the report: the API's `normal_lane` isn't that subset). |
| T5 | should-fix | Toast, dialog and subtitle said everything "moves to re-review". | Fixed. Toast: "9 live items move to Needs re-review; 5 expire."; subtitle: "…sends live items that quote the old one to Needs re-review; the rest expire." |
| T6 | should-fix | Dialog lacked counts and irreversibility; table below the fold. | Fixed. Dialog lists Needs re-review, Expire, In re-review (when any) and Partners, then "Can't be undone: publishing the old values creates v14 and re-sends these items." The panel has a "14 affected items ↓" button that scrolls to and focuses the table. |
| T7 | should-fix | Tab switches and impact links dropped unsaved edits. | Fixed. Impact partner and item links open a new tab (`target=_blank rel=noopener`). While the form is dirty (a changed field or a note) the other product tabs are disabled, with "Publish or cancel your personal loan edits to switch products." beside them. |
| T8 | should-fix | Preview skeleton about 110px against about 320px loaded. | Fixed. The skeleton draws the summary, the counts row, two lines and two partner rows in the loaded elements' type: 317px both, measured on the 1280 screenshots. |
| T9 | nit | "Terms" collided with "Offer terms". | Fixed. "Loan terms (months)" in the form and the history diff labels. |
| T10 | should-fix | Screenshots stale; Will become (8.5rem) too narrow for "Needs re-review". | Fixed. 10.5rem; all screenshots recaptured at head. |
| T11 | should-fix | `.app-terms-panel` `outline-none` hid the focus ring on focusable empty panels. | Fixed. `.app-terms-panel[data-focus-visible]` draws the ring (one rule with P8's). |
| T12 | should-fix | Focus dropped to body when the editor opened or closed. | Fixed. The first field takes focus on open; Cancel or Publish returns it to Edit terms (or Publish first terms). Tested on Cancel. |
| T13 | nit | Truncated Quotes and Title cells; bold-only "changes". | Fixed. Both cells carry `title`; changing fields have sr-only "(changes)". |
| T14 | nit | Truncated Issuing bank value. | Fixed. Every in-effect value cell has `title`. |
| T15 | should-fix | One message for every kind; "up to 100%" was wrong. | Fixed. Format and range messages per kind (APR, percent, dollars), "from 0% to below 100%", and %/$ adornments inside the inputs. |
| T16 | nit | The tab-count placeholder shifted the tabs between states. | Fixed. Tabs that can have a count keep a fixed-width slot in every state; it's only visible while loading. |
| T17 | nit | Counts announced three times. | Fixed. The tile's group label is the only name; its children are `aria-hidden`. |

Found while recapturing, and fixed: at 1280 the tile labels broke at "re-\nreview" (the status mark moved to the
figure, labels don't wrap, "Already in re-review" became "In re-review now"); "0 get new numbers" on an empty tile
(now "none"); the dialog's two lists had different label widths.

## Partners (`/partners`)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| P1 | should-fix | Reviewers can't reach `/partners/$id`: the nav is lead-only and the review Details tab shows the partner as text. | Fixed after the orchestrator's ruling (PR 3). Offer terms and Partners are in reviewers' nav; both are read-only for reviewers, and the server allows the reads (only agreement attachments are role-gated, and reviewers may read them). The review Details tab links the partner name to `/partners/$partnerId`. Tests: `nav.test.ts` and `ReviewPage.test.tsx`. |
| P2 | should-fix | Repeat issues showed only the raw rule id. | Fixed. `RepeatIssueOut.rule_title` (backend, test first) from the engine registry or the AI rules, null when neither knows the id. `listPartnerFindings` takes `rule_id`. Each repeat issue's title links to `?tab=findings&rule=<id>`; the history then says "Only <title>" with "Show all findings". `make schema` run. |
| P3 | should-fix | Detail skeleton header about 36px short. | Fixed. Each skeleton bar sits in the real element's type (crumbs, h1, stat figure and label); the tabs sit at the same y loaded and loading. |
| P4 | should-fix | Legacy tag cut off in the truncating title cell. | Fixed. It sits beside the item key. |
| P5 | should-fix | Two labels and two date formats. | Fixed. "Open findings" on the list, the detail stat and the items tab column; last submitted is a date on both pages. |
| P6 | should-fix | "No agreement on file" for roles that can't see agreements; Retry offered on a 403. | Fixed. Roles without reviewer or admin see "Agreements are visible to reviewers and leads."; Retry shows only for 5xx or network errors (`ui/errorMessage.ts` `isRetryable`), on both pages. |
| P7 | nit | Severity loud on resolved findings; citations wrapped. | Fixed. Non-open findings get a quiet outline badge; citations are `nowrap`. |
| P8 | should-fix | `.app-partner-panel` hid the focus ring. | Fixed with T11's rule. |
| P9 | should-fix | Focus dropped on Edit details and New partner. | Fixed. Name takes focus on open; Cancel or Save returns it to Edit details; Cancel on a new partner returns it to the New partner button. Tested on Edit details. |
| P10 | nit | Findings history had no count. | Fixed. The loaded count, "+" when there are more pages ("3+"). |
| P11 | nit | "No submissions" when items exist; date copy. | Fixed. "—", which is now always right: `submitted_at` is non-null on every item, imports included, so `last_submitted_at` is null only with no items and "Imported only" can't occur. Date error: "Pick a date." Sorting left alone. |
