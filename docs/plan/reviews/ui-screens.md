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
