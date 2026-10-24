# Report: queue table, board, preview drawer (workstream H, part 2)

Part of #9. Branch `wsH/queue`. Plan: `docs/plan/queue.md`. UI review: `docs/plan/reviews/ui-queue.md`,
screenshots in `docs/plan/reviews/ui/queue/` (16 states × 1440×900 and 1280×800).

Execution: native. Every task consumed the same three interfaces (the URL search schema, `ItemRowOut` cells,
and the `['/api/items']` cache keys), so per-task subagents would each have re-derived them. One fresh UI
reviewer ran on the screenshots at the end (spec §8.4).

Naming: issue #9 says `frontend-queue.md`; the task brief says `queue.md`. Followed the brief.

## What shipped

| Area | Where | Notes |
|---|---|---|
| URL contract | `features/queue/search.ts` | zod v4 schema passed straight to `validateSearch`; every field `.catch()`-guarded, so a stale or hand-edited URL drops the bad field instead of throwing. A URL with no filters and no view opens My queue. Filters, sort, layout, and the open preview item are all in the URL. |
| Views | `search.ts`, `ViewBar.tsx` | Built-ins: My queue `{mine}`, Unassigned `{unassigned}`, Waiting >3 days `{waiting: 3}`, Needs re-review `{reopen_reason: all three}`, All active `{status: submitted, in_review, changes_requested, needs_rereview}`. Saved views via `GET/POST/DELETE /views` store filters, sort, and visible columns. The active view is derived from the URL; "Modified" shows when filters or sort move off it. |
| Table | `QueueTable.tsx`, `columns.tsx` | TanStack Table 9.3.1 with explicit features (sizing, resizing, visibility, row selection). Native `<table>`; rows are one roving tab stop. Resizable columns (mouse + touch, double-click resets, widths persisted per browser). Title is the flexible column. Default columns fit 1280px; Product, Channel, Re-review reason, Tags are in the chooser. With the preview open, Risk, Partner, Assignee, and Round step aside (the drawer shows them). The whole select cell is the checkbox's hit area. |
| Sorting | `columns.tsx` `SORT_CYCLES`, `FilterBar.tsx` `SortMenu` | Server-owned. Title header → `title`; Age header cycles oldest → newest → queue order; Sort menu offers all five `ItemSort` orders. Other headers have no sort affordance (see API gaps). |
| Pagination | `useQueueItems.ts`, `QueueFooter.tsx` | `useInfiniteQuery` over the generated `listItems` + `getListItemsQueryKey` (key suffixed `'pages'` so it never collides with a single-page `useListItems` entry). 50 per page; a sentinel loads the next page on scroll; "Load more" is the keyboard path. A failed later page keeps the loaded rows and shows the server's message with Reload. |
| Filter bar | `FilterBar.tsx` | Search (title or `CP-…`, 250 ms debounce) and chips: Status, Risk, Assignee (Me / Unassigned / a reviewer), Partner inline; Product, Channel, Findings, Waiting, Re-review reason under More filters (submenus) until set, then inline. Each chip names its choice and has its own clear. "Clear filters" returns to the active view's own filters. |
| Stats strip | `StatsStrip.tsx` | Real numbers from `/items/stats`. My queue / Unassigned / Waiting >3 days / Needs re-review open their view; In queue is a plain figure (no view matches it exactly). |
| Inline edits | `RiskCell.tsx`, `TagsCell.tsx`, `TagEditor.tsx`, `AssigneeCell.tsx`, `useItemPatch.ts`, `useAssignment.ts` | Risk tier for reviewers and leads; tags (and notes, in the drawer) for the submitter or a reviewer, mirroring `update_item_fields`: optimistic across every cached list and the item detail; on error the snapshot is restored and a toast gives the server's message. Assignee: Claim on unassigned submitted items (reviewers, leads), a reassign menu for leads/admins and a reviewer's own item; not optimistic (the server decides who wins a claim). Edit controls are tab stops only in the active row. |
| Bulk actions | `BulkBar.tsx` | Floats at the bottom of the list while rows are selected (filters and rows don't move). Leads/admins: Assign… (`POST /items/bulk/assign`). Leads with a re-review selected: Fast-track N re-reviews… with a required reason (`POST /items/bulk/fast-track-approve`). Skipped items stay selected and the toast lists why. Selection resets when the result set changes. |
| Board | `Board.tsx` | Submitted · In review · Changes requested · Needs re-review · Approved · last 14 days. Two list queries (the four active statuses explicitly, since `changes_requested` isn't a queue status; and `approved` + `approved_within_days=14`). Only Submitted → In review drags (React Aria DnD, keyboard included) or uses the card's Claim button → `POST /items/{id}/claim`. Every card press opens the preview. The Status chip is hidden on the board (columns are statuses). |
| Preview drawer | `PreviewDrawer.tsx` | Non-modal `<aside>` beside the list, so j/k keep moving and the drawer follows. Status, risk, re-review reason, Open review (link to `/items/{id}`, shortcut `o`), open findings by severity (from `GET /items/{id}/findings`, open only), latest decision (outcome, approver, version, date, reason), facts, notes, tags. 404 and error states. |
| Keyboard | `keyboard.ts`, `ShortcutsDialog.tsx`, `QueuePage.tsx` | Pure `queueKeyAction(event)`: j/↓ next, k/↑ previous, Enter preview (focus moves into the drawer once it loads), o open review, x select, ? help, Esc close. Ignored in text fields, comboboxes, open menus, and modal dialogs; Enter and x are left to buttons and checkboxes. |
| States | `QueuePage.tsx` | Loading skeleton with the visible columns' widths; empty per view ("Nothing assigned to you · 4 unassigned items" + Show unassigned; "No items match these filters" + Clear filters; search-specific copy); error with the server's message + Retry; partial (stats, saved views, and later pages fail inline while the rest works). |
| Shell wiring (#20) | `ui/layout/SessionGate.tsx`, `SignIn.tsx`, `session.ts`, `Viewer.tsx`, `UserMenu.tsx`, `routes/__root.tsx` | The root route resolves the viewer from `GET /api/me` (`effective_roles` drive the nav and every role-gated control). 401 shows a minimal sign-in (allauth headless browser flow: GET session issues the CSRF cookie, POST login). The account panel shows email and roles and signs out. `DEMO_VIEWER` and "No sign-in yet" are gone. |
| Generated enums (#20) | `ui/domain.ts` | Re-exports the generated `ItemStatus`, `RiskTier`, `Severity`, `FindingSource`, `Role` (no hand-mirrored literals); kept as a module so workstream I's imports don't break. |
| Compact status badge (#20) | `ui/badges.tsx` `StatusMark` | Icon-only, `role="img"` + `aria-label` + `title`, no tab stop (the row is the tab stop). `RiskTierBadge` gained an additive `short` prop for the Risk column. |
| Icons | `ui/icons.ts` | +17 keys: `view.table/board`, `action.columns/save_view/keyboard/reload/drag/sign_in/open`, `entity.user/tag`, `sort.ascending/descending/none`. `action.open` (ArrowRight) is same-tab navigation; `open_external` stays for new tabs. Identity test passes with no new allowlist entries. |

## Interaction model

- One URL per queue state: `/?view=unassigned&unassigned=true&risk_tier=["high"]&item=1047&layout=board`.
  Filters and view switches push history; opening/closing the drawer and j/k replace it.
- One tab stop for the list (the active row); j/k move it, Enter previews, o opens the review, x selects. The
  active row has a navy leading bar; keyboard focus draws a 2px inset ring on the row.
- Clicks inside inline editors, checkboxes, and their popovers never reach the row (React events bubble through
  portals, so `stopRowClick` sits on the cell wrapper).

## API gaps found (not changed here; generated code and openapi are other workstreams')

1. **`ItemSort` covers five orders.** Status, risk tier, assignee, partner, open findings, and round can't be
   sorted server-side, so those headers don't sort. Spec §5.3 wants every column sortable. Cheapest fix (backend
   owner): add those members to `ItemSort` and `_SORTS` (each needs a single-direction key ending in `id` for
   the keyset). The frontend change is one entry per column in `SORT_CYCLES`.
2. **`ItemRowOut` has no `notes`**, so notes are edited in the drawer, not inline in the table.
3. **No total count on `ItemPageOut`.** The footer says "50 items loaded" rather than "50 of 312".
4. **`QueueStats.needs_rereview` counts `status = needs_rereview` only**, while the Needs re-review view keys on
   `reopen_reason` (so a re-review a reviewer has opened stays in it, matching queue priority). The two numbers
   can differ by the re-reviews in review. Fix: count `reopen_reason IS NOT NULL AND status IN QUEUE_STATUSES`.
5. **Stats exclude legacy items; `GET /items` doesn't.** Queue statuses rarely hold legacy items, but a
   `is_legacy=false` default on the queue sort would make them agree by construction.
6. **`POST /views` has no update.** Saving a modified saved view creates a new one.
7. **Claim, assign (single and bulk), and bulk fast-track are stubs (501) today** (workstreams E and F). The UI calls the
   generated hooks and shows the server's message on failure; the MSW mocks cover the success paths.
8. **Dev CSRF origins are hardcoded** in `backend/config/settings/dev.py` (`localhost:5173` only), so a Vite dev
   server on any other port can't sign in. Not a bug in prod; worth reading from `DJANGO_CSRF_TRUSTED_ORIGINS`.

## UI review findings and resolutions

Full table: `docs/plan/reviews/ui-queue.md`. Fresh reviewer, 32 screenshots, spec §5 + make-interfaces-feel-better.
No blockers; 13 should-fix, 8 nits, 3 polish, 3 fixture problems in the evidence. All fixed except Q10 (partly:
Round stays per the brief, so Title still truncates at 1280) and two accepted residuals (a saved-views failure at
1280 with a long Status chip, and a heavily modified filter bar, can each wrap the filter row to a second line).
The themes and what changed:

- **Stable layout (§5.3)**, the bulk of it: the bulk bar now floats instead of replacing the filter row; the
  skeleton is the real table; the stats strip holds its height on error; the view row never wraps; less-used
  filters moved under More filters; the drawer hides the columns it shows; the board fits 1280.
- **Color meaning (§5.2)**: the selected tint was info-blue by the numbers; now near-neutral.
- **Missing capability**: assignee wasn't editable inline (product-spec Queue lists it); now Claim / reassign.
- **Hit areas**: checkbox cell, chip clear, and drag handle meet the 24px floor.
- **Copy/consistency**: stat labels match their tabs; "Approved · last 14 days"; market labels; open icon.
- Also found and fixed in my own pre-review pass: the table scrolled sideways at 1280 and the sign-in card was off
  center (my first centering attempt didn't fix it; the reviewer found the grid-column cause).

## Verification

Final run on the rebased branch (on origin/main `ff5a938`), from `frontend/`:

```
npm run lint            eslint .                                  (clean)
npm run format:check    All matched files use Prettier code style!
npm run typecheck       tsc -b                                    (clean)
npm run test:run        Test Files 25 passed (25) · Tests 263 passed (263)
npm run build           ✓ built in 337ms · routes 306.84 kB (gz 77.21) · index 542.28 kB (gz 168.95)
npm run test:browser    Test Files 2 passed (2) · Tests 7 passed (7)
E2E_PORT=4391 npm run test:e2e    9 passed · 32 skipped (screenshot spec, SCREENSHOTS=1 only)
SCREENSHOTS=1 …         32 passed (UI review captures)
```

The build still warns that `index` is over 500 kB (pre-existing; the queue route now splits into its own chunk,
which took `index` from 671 kB to 542 kB).

**Real backend check** (not a CI gate): this branch's Django server against a private `clearpath_wsh` database
(migrated, demo users seeded), Vite on :5173, scripted with Playwright:

- Sign-in and sign-out (allauth headless with CSRF) work for marketer and reviewer.
- 4 items submitted via `POST /api/items` → 201 (CP-1…CP-4).
- The reviewer's My queue is empty: "Nothing assigned to you · 4 unassigned items"; Show unassigned → 4 rows in
  queue order.
- Inline risk change → `PATCH` 200 `low`.
- The Product chip sends `?product=credit_card&unassigned=true&sort=queue&limit=50`; the rows narrow.
- Save view → `POST /api/views` 201 and the URL becomes `view=saved:N`; a duplicate name gets a 422, shown inline.
- Stats strip shows real counts; the drawer loads detail plus findings ("No open findings"); the board loads lanes.
- No 4xx/5xx other than the expected `/api/me` 401 before sign-in.

Not exercisable: claim/assign/bulk (501 stubs).

## Files touched outside the listed ownership

- `frontend/src/theme/theme.css`: one appended block (`/* ---- Queue … */`) with one new token pair
  (`--color-selected`, `--color-selected-hover`); no existing rule edited. It's the only legal home for `app-*`
  classes (frontend/CLAUDE.md).
- `frontend/src/test/server.ts` (default MSW handlers for items, me, users, findings, decisions, partners),
  `src/test/setup.ts` (jsdom `scrollIntoView` stub), new `src/test/renderApp.tsx`, `src/test/browserApi.ts`.
- `frontend/e2e/shell.spec.ts` (now stubs `/api/me` and the queue), new `e2e/api.ts`, `e2e/queue.spec.ts`,
  `e2e/screenshots.spec.ts` (skipped unless `SCREENSHOTS=1`).
- `frontend/playwright.config.ts`: `E2E_PORT` override (default 4173 unchanged). Parallel worktrees were
  sharing port 4173 with `reuseExistingServer`, so one run could test another branch's build.

## Deferred and risks

- **Review route link is a string.** `/items/$itemId` belongs to workstream I and isn't in this branch's route
  tree, so `reviewPath()` + `router.history.push` stand in for a typed `<Link>`. Swap when I merges (one file).
- **Sign-in is minimal by design**: no password reset, no MFA step (a 401 from login says so), no signup.
- **Board shows the first 200 items per query** and says so when truncated.
- **Keyboard column resizing** isn't offered (pointer only); every column can also be hidden.
