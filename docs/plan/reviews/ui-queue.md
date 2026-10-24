# UI review: Queue (table, filters, views, board, preview drawer)

Workstream H part 2, branch `wsH/queue`. Spec §8.4 review: a fresh reviewer read spec §5, product-spec
"Screens" and "Board view", reports/design-system.md, and the make-interfaces-feel-better skill, then viewed every
screenshot. Screenshots: `docs/plan/reviews/ui/queue/<state>-<width>.png`, 16 states at 1440×900 and 1280×800,
captured by `frontend/e2e/screenshots.spec.ts` (`SCREENSHOTS=1`) against the production build with stubbed API.

States: table (All active), loading, empty-my-queue, empty-filtered, error, partial (counts + saved views failed),
drawer, board, filter-menu, more-filters (added after review), bulk-selection, inline-risk, columns, shortcuts,
focus-row, sign-in.

Pre-review pass (before dispatching the reviewer, from my own look at the first capture): the table scrolled
sideways at 1280 (Round cut off), so Title became the flexible column, Product/Channel/Re-review reason/Tags are
hidden by default, Risk shows "High" under the Risk header, and Sort moved into the toolbar.

Verdict: no blockers; 13 should-fix, 8 nits, polish items. All fixed except where noted. Most should-fixes were
§5.3 "stable layout" violations: content moving when selection starts, data loads or fails, or a view is modified.

## Findings and resolutions

| ID | Sev | Finding (abridged) | Resolution |
|---|---|---|---|
| Q1 | should-fix | `--color-selected` (95.5% 0.018 262) is the info-soft tint (95.5% 0.022 250): selected rows and active chips read as "In review", the prior review's #4 again. | Fixed. `--color-selected: oklch(95% 0.005 258)` (nav-active's chroma). Navy stays on the checkbox, chip border, and the active-row bar. |
| Q2 | should-fix | Bulk bar replaced the filter row: the table jumped 26px on the first checkbox click, and the active filters disappeared while bulk-acting. | Fixed. The filter row stays; the bulk bar floats `sticky bottom-2` inside the list region (overlay shadow, as an overlay). Test: "keeps the filters in place while rows are selected". |
| Q3 | should-fix | Row checkbox was a 14×14 target; a near miss opened the preview. | Fixed. A `<label>` fills the 36px select cell and stops the row click. Test: "selects from anywhere in the checkbox cell". |
| Q4 | should-fix | Skeleton didn't match: no header row, grid gaps offset bars ~116px, ignored resized widths; stat skeleton 20px vs 24px figure. | Fixed. `QueueSkeleton` renders the real `<table>`: header labels, the same colgroup (resized widths from storage), bars inside `.app-td`. Stat skeleton `h-6`. |
| Q5 | should-fix | Counts failing collapsed the stats strip (list jumped 16px); saved-views error looked attached to "All active" and had no icon. | Fixed. `.app-stats` keeps `min-h-12`; the saved-views error has the error icon and moved to the filter row. See residual R1. |
| Q6 | should-fix | At 1280, "Modified · Save view" or the saved-views error pushed the toolbar to a second line (table jumped 38px). | Fixed. The view row never wraps (`flex-nowrap`; tabs `min-w-0 overflow-x-auto`); the Sort button shows just the order ("Queue order", named "Sort: Queue order"), so tabs + Modified + Save view + toolbar fit 1280. |
| Q7 | should-fix | Filter bar wrapped to two rows depending on the active chip's label; "Re-review reason" orphaned at 1440. | Fixed. Status, Risk, Assignee, Partner inline; Product, Channel, Findings, Waiting, Re-review reason under **More filters** (each a submenu with the chip's own choices) until set, then inline as a chip. Chip labels cap at `max-w-56`; search `w-48`. Test: "keeps less-used filters under More filters until they have a value". |
| Q8 | should-fix | With the drawer open the table clipped mid-word ("Dana Whitfie", "Partne") and hid Findings/Age/Round behind an invisible horizontal scroll. | Fixed. While the drawer is open Risk, Partner, Assignee, and Round step aside (the drawer shows all four); Item, Title, Status, Findings, Age fit beside it at 1280. Test: "steps Risk, Partner, Assignee, and Round aside while the preview is open". |
| Q9 | should-fix | Board lanes `minmax(13rem)` overflowed 1280 by 56px; the Approved lane was cut. | Fixed. `minmax(12rem,1fr)`. |
| Q10 | should-fix | Title gets ~198px at 1280 while Status reserved 172px. | Partly. Measured the widest badge ("Changes requested") at 144px + 16px padding, so Status is 168px (160 clipped it). Round stays visible by default: it's in the brief's column list and costs 56px. Title still truncates at 1280 (full text on hover and in the drawer). Judgment. |
| Q11 | should-fix | No way to take an item from the table; product-spec lists assignee among inline edits. | Fixed. `AssigneeCell`: **Claim** on unassigned submitted items for reviewers/leads (`POST /items/{id}/claim`); a reassign menu for leads/admins and for a reviewer's own item (`POST /items/{id}/assign`), matching `backend/reviews/api.py` claim/assign docstrings. Shared `useAssignment.ts` (the board's Claim uses it too). Tests: claim, no claim on someone else's item, lead reassign. Both endpoints are 501 stubs until workstream E. |
| Q12 | should-fix | "Open review" used `action.open_external` (new-tab glyph) for same-tab navigation. | Fixed. New registry key `action.open` (ArrowRight). |
| Q13 | should-fix | Sign-in card off-center: `.app-topbar` is `col-span-2`, creating an implicit second column. | Fixed. `.app-signin > .app-topbar { col-span-full }` (additive; the shell rule is unchanged). |
| Q14 | nit | Risk picker marked the current value only by weight. | Fixed. Same check column as the filter menus. |
| Q15 | nit | "Mine" stat vs "My queue" tab; "Re-review" stat vs "Needs re-review" tab. | Fixed. Stats say "My queue" and "Needs re-review", matching the tabs they open. |
| Q16 | nit | Empty partner shown as "No partner" on cards (but "—" elsewhere) and truncated first. | Fixed. Omitted when null; assignee is `shrink-0`. |
| Q17 | nit | "Approved (14 days)" reads as "approved for 14 days". | Fixed. "Approved · last 14 days". |
| Q18 | nit | Sortable headers looked like the rest at rest. | Fixed. Sort glyph at 0.4 opacity at rest on Title and Age. |
| Q19 | nit | Error state looked like an empty state. | Fixed. The error glyph takes `status-error-soft-content`. |
| Q20 | nit | Markets read "national, CA". | Fixed. `MARKET_LABEL` → "National, CA". |
| Q21 | nit | Demo-account rows didn't look clickable. | Fixed. "Pick one to fill in the email." under the heading. |
| P1 | polish | Chip clear 20×20, card drag handle 20×20 (below the 24px floor). | Fixed. Both 24×24. |
| P2 | polish | Segmented control radii not concentric (4 outer, 2 padding, 3 inner). | Fixed. Items `rounded-xs` (2px). |
| P3 | polish | Demo account text 6px right of the heading. | Fixed. List `-mx-1.5` so text aligns and hover bleeds out. |
| F1–F3 | evidence | Fixture contradictions: empty My queue beside "8 Mine"; rows not in queue order under "Sort: Queue order"; shortcuts shot caught mid-fade. | Fixed in `e2e/api.ts` (stats override, server's queue order: re-reviews, risk, age) and a 400ms settle. |

## Residual (known, accepted)

- **R1.** When saved views fail at 1280 *and* a long Status chip is active, the saved-views error wraps to a second
  filter line, so the list moves 34px once when the failure lands. Fitting it on the view row would mean clipping
  tabs. A rare failure path; recorded rather than squeezed.
- **R2.** A modified view with several active chips (e.g. Risk + Assignee + Product) can still wrap the filter bar
  to a second line at 1280 ("Clear filters" moves down). Chips name their choice, so their width varies by design.
- **R3.** Title truncates at 1280 with every default column on (Q10).

## Keep (reviewer's list, re-checked after fixes)

Re-review is the only solid badge; risk tier has no status color; the keyboard focus ring (2px navy) is distinct
from the active-row bar; inline-edit carets appear only on the active row; empty states say why plus the next
action, left-aligned; bulk actions name their count; partial failures are one-line, per region, with Retry; drawer
severities use color + glyph + words; 36px rows, flat surfaces, shadows only on overlays; tabular figures.
