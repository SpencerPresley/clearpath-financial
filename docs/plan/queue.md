# Queue: table, board, preview drawer — implementation plan (workstream H, part 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The reviewer's queue: a dense, URL-addressable table with filters, saved views, bulk assign, inline
edits, a stats strip, a board toggle, a preview drawer, and a keyboard path; plus the shell wired to `/api/me`.

**Architecture:** Route `/` validates a zod v4 search schema (`features/queue/search.ts`), so filters, sort,
layout, and the open drawer item are the URL. The table is TanStack Table v9 (`useTable`, explicit features,
`manualSorting`) over a `useInfiniteQuery` keyset list built from the generated `listItems` /
`getListItemsQueryKey`. Board, drawer, stats, and views are separate regions with their own queries, so one
failing region doesn't take the page down. The root route resolves the viewer from `GET /api/me`; a 401 shows
a one-form sign-in (allauth headless).

**Tech stack:** React 19, TanStack Router 1.170 / Query 5 / Table 9.3.1, React Aria Components 1.22.1, zod 4,
Tailwind v4 + daisyUI, Vitest + Testing Library + MSW (generated handlers), Playwright.

**Spec:** `docs/spec.md` §1, §4.3 Review, §5 (binding), §8.4; `docs/product-spec.md` Screens (Queue, Board
view); `docs/decisions.md` "Ergonomics", "Queue views", "Reviewer assignment"; `docs/plan/reports/foundation.md`
(API); `docs/plan/reports/design-system.md` (tokens, components, icons); GitHub #20.

## Global constraints

- Only generated hooks/functions reach the API (`src/api/generated/**`, never hand-edited); every request goes
  through `mutator.ts`.
- Icons only via `<Icon name>` and registry keys in `src/ui/icons.ts`; no two keys share a glyph unless
  allowlisted (`icons.test.ts`). Icons accompany labels except in dense cells, where they get a tooltip/title
  and `aria-label` (§5.2a).
- Only ClearPath tokens; component classes are `app-*` in `src/theme/theme.css`, added as one delimited
  `/* ---- Queue ---- */` block appended at the end (workstream I appends too; never edit existing rules).
- Copy uses the glossary exactly: Item (`CP-1042`), Version, Round, Finding, Decision, Re-review, Partner.
  Status labels come from `STATUS_META`. AI is "AI suggestion". No "Violation". Errors: what happened + what to
  do, one line.
- No dead buttons, no "coming soon" (spec §2 anti-goal). An action the viewer can't take is not shown.
- Queue default order: re-reviews first, then risk tier, then age (= server `sort=queue`).
- Tables: 36px rows (`h-row`), tabular figures, skeletons match the table's real column widths.
- Status pairs color with label + icon; never color alone.
- Gates: `npm run lint`, `format:check`, `typecheck`, `test:run`, `build`, `test:browser`, `test:e2e`.

## Decisions (judgment, with the mechanism)

- **Sort is server-only.** `_SORTS` in `backend/reviews/selectors.py` offers queue / oldest / newest / updated /
  title, each one direction, keyset cursor bound to the sort. Client-sorting the loaded page would show an order
  the next page contradicts. Sortable headers: Title (`title`), Age (`oldest` ↔ `newest`), plus a Sort menu with
  the five orders. Other columns show no sort affordance; missing `ItemSort` members go in the report as an API gap.
- **Keyset "load more", not virtualization.** 50 rows a page, a sentinel auto-loads the next page on scroll and a
  "Load more" button is the keyboard path. No new dependency (`@tanstack/react-virtual` isn't installed).
- **Built-in views are client constants; custom views persist via `/views`** (create + delete; there is no
  update, so "Save" on a modified saved view is "Save as new view"). The active view is derived by matching
  the URL's filter state against each view's definition; a mismatch reads "Modified".
  - My queue `{ mine: true }` · Unassigned `{ unassigned: true }` · Waiting >3 days `{ waiting: 3 }` ·
    Needs re-review `{ reopen_reason: all three }` · All active `{ status: submitted, in_review,
    changes_requested, needs_rereview }`.
  - Needs re-review keys on `reopen_reason`, not `status=needs_rereview`: the foundation report shows a
    status key drops the item as soon as a reviewer opens it (in_review). Cost: the stats strip's
    `needs_rereview` counts status only, so the two numbers can differ (API gap).
- **Preview drawer is a non-modal `<aside>`**, so j/k keep working and update it. `item` is a search param.
- **"Open review" links to `/items/$itemId`** (built by workstream I). The route isn't in this branch's route
  tree, so `reviewPath(id)` returns a string and navigation goes through `router.history.push`; swap to a typed
  `<Link>` when I merges.
- **domain.ts becomes re-exports of generated enums** (keeps import paths stable for workstream I).
- **Sign-in gate added** (no workstream owns login; without it real roles can't load). One form, email +
  password → `POST /_allauth/browser/v1/auth/login`; sign-out in the account panel. No reset/MFA.
- **Bulk fast-track** wired to `useBulkFastTrackApprove`, shown only to leads when the selection contains a
  `needs_rereview` item; requires a reason (API requires one). The server (workstream F) owns success.
- **Screenshots and e2e stub the API with `page.route` fixtures** (no seed exists until workstream L).

## Review focus (inputs no task's happy path exercises)

1. A hand-edited/stale URL (`?status=bogus&risk_tier=7`) must render the queue with the bad fields dropped,
   not throw. → Task 1 test `drops invalid fields instead of throwing`.
2. An inline edit that fails (403 for a marketer editing risk, 422 tag too long) must restore the old value and
   say why. → Task 4 test `rolls back and toasts the server message on error`.
3. Keyboard shortcuts must not fire while typing in a filter, tag editor, or the drawer's notes. → Task 6 test
   `ignores keys from editable targets`.
4. A `cursor` that went stale (server 422 "This page link is out of date") must offer reload, not loop. →
   Task 3 test `shows the server message with Reload when a later page fails`.
5. Bulk assign where some items are skipped (`BulkResultOut.skipped`) must report the count and reasons and keep
   the skipped items selected. → Task 7 test `keeps skipped items selected and reports them`.

---

### Task 1: Search schema, views, and list params

**Files:** Create `frontend/src/features/queue/search.ts`, `search.test.ts`.

**Interfaces — produces:**
- `queueSearchSchema` (zod object, every field `.catch()`-guarded): `view?: string`, `q?: string`,
  `status?: ItemStatus[]`, `product?: Product[]`, `channel?: Channel[]`, `risk_tier?: RiskTier[]`,
  `reopen_reason?: ReopenReason[]`, `partner_id?: number[]`, `assignee_id?: number[]`, `mine?: boolean`,
  `unassigned?: boolean`, `has_open_findings?: boolean`, `waiting?: number`, `sort: ItemSort` (default
  `queue`), `layout: 'table' | 'board'` (default `table`), `item?: number`.
- `type QueueSearch = z.output<typeof queueSearchSchema>`; `type QueueFilters` = the filter subset.
- `DEFAULT_SEARCH: QueueSearch` = My queue.
- `BUILT_IN_VIEWS: readonly BuiltInView[]` (`{ id, label, filters: QueueFilters }`), ids `mine | unassigned |
  waiting | rereview | active`.
- `toListParams(search, extra?: { cursor?, limit? }): ListItemsParams`.
- `filtersOf(search): QueueFilters`; `sameFilters(a, b): boolean` (order-insensitive arrays, absent = empty).
- `activeView(search, saved: SavedViewOut[]): { kind: 'builtin' | 'saved' | 'custom', id?, label, modified }`.
- `savedViewToSearch(v: SavedViewOut): QueueSearch`; `searchToSavedViewIn(name, search, columns): SavedViewIn`.

- [ ] Tests: default search equals My queue; `drops invalid fields instead of throwing` (`status: ['bogus']`,
      `risk_tier: 7`, `item: 'x'` → those keys absent, rest kept); `toListParams` maps `waiting` →
      `waiting_more_than_days`, omits empty arrays/false booleans, passes `sort`; `activeView` finds built-ins
      regardless of array order, reports `modified` when a filter is added on top of a view, and resolves a saved
      view by `view=saved:<id>`; saved-view round trip preserves filters and sort.
- [ ] Implement; enum values from the generated `const` objects (`Object.values(ItemStatus)`).
- [ ] Commit `Queue: search schema, built-in views, list params`.

### Task 2: Generated enums, compact status mark, icons, theme block

**Files:** Modify `src/ui/domain.ts` (re-exports + `ITEM_STATUSES = Object.values(ItemStatus)` etc.),
`src/ui/badges.tsx` (add `StatusMark`), `src/ui/icons.ts` (+ keys), `src/ui/badges.test.tsx`,
`src/theme/theme.css` (append Queue block). Create `src/features/queue/labels.ts` (+ test).

**Interfaces — produces:**
- `StatusMark({ status })`: icon-only status for dense cells: `<span role="img" aria-label="In review"
  title="In review" class="app-status-mark" data-tone>`; no tab stop (rows are the tab stop).
- Icon keys: `view.table` (Table), `view.board` (Kanban), `action.columns` (Columns), `action.save_view`
  (BookmarkSimple), `action.keyboard` (Keyboard), `action.select` (CheckSquare), `entity.user` (User),
  `action.reload` (ArrowClockwise).
- `labels.ts`: `PRODUCT_LABEL`, `CHANNEL_LABEL`, `REOPEN_REASON_LABEL` (`Terms changed`, `Approval expired`,
  `Drift detected`), `OUTCOME_LABEL`.

- [ ] Tests: `StatusMark` has accessible name = `STATUS_META` label and the status tone; labels cover every
      enum member (`Object.values(Product).every(...)`). Existing icons test still passes with new keys.
- [ ] Implement; run `npx vitest run --project unit src/ui src/features/queue/labels.test.ts`.
- [ ] Commit `UI: generated enums, compact status mark, queue icons`.

### Task 3: Queue data hooks and the table

**Files:** Create `features/queue/useQueueItems.ts`, `columns.tsx`, `QueueTable.tsx`, `QueueTable.test.tsx`,
`fixtures.ts` (test + e2e fixtures: `makeRow(overrides): ItemRowOut`, `ROWS`). Modify `src/test/server.ts`
(add generated items, me, users, findings, decisions, partners mocks as defaults).

**Interfaces — produces:**
- `useQueueItems(search)`: `useInfiniteQuery({ queryKey: getListItemsQueryKey(toListParams(search)),
  queryFn: ({ pageParam, signal }) => listItems(toListParams(search, { cursor: pageParam }), { signal }),
  initialPageParam: null, getNextPageParam: p => p.next_cursor })` → `{ rows, query }`; `rows` memoized,
  module-level `EMPTY_ROWS`.
- `QUEUE_COLUMNS` ids: `select, key, title, status, risk_tier, product, channel, partner, assignee,
  open_findings, age, round, reopen_reason, tags`; `DEFAULT_HIDDEN = { channel: false, tags: false }`; sizes in px.
- `QueueTable({ rows, search, onSearch, activeId, onActiveChange, onOpen, selection, onSelectionChange,
  columnVisibility, onColumnVisibilityChange, canEdit })`. Features: `columnSizingFeature,
  columnResizingFeature, columnVisibilityFeature, rowSelectionFeature, rowSortingFeature`; `getRowId: r =>
  String(r.id)`; `manualSorting: true`; sizes persisted in `localStorage['clearpath.queue.sizes']`.
- Native `<table>` with `table-layout: fixed` and widths from `header.getSize()` as CSS vars; resize handle on
  `mousedown` + `touchstart` (`header.getResizeHandler()`), double-click resets; rows roving `tabIndex`.

- [ ] Tests: renders one row per fixture with key, title, status label, risk, partner, assignee, open findings
      count, age (`3d`), round (`R2`), re-review reason; clicking the Title header sets `sort=title`, Age header
      toggles `oldest`/`newest`; Status header has no sort button; hiding a column via the chooser removes its
      header; checkbox click selects without opening; row click calls `onOpen`.
- [ ] Test `shows the server message with Reload when a later page fails` (page 2 → 422 ErrorOut).
- [ ] Implement; commit `Queue: table with resizable columns, server sort, selection`.

### Task 4: Inline edits (tags, risk tier) with optimistic rollback

**Files:** Create `features/queue/useItemPatch.ts`, `TagsCell.tsx`, `RiskCell.tsx`, `useItemPatch.test.tsx`.

**Interfaces — produces:** `useItemPatch()` → `mutate({ id, patch: ItemUpdateIn })`. `onMutate`: cancel
`['/api/items']`, snapshot every matching infinite cache and `getGetItemQueryKey(id)`, patch the row;
`onError`: restore + `showToast({ tone: 'error', title: "Couldn't save CP-…", description: ErrorOut.message })`;
`onSettled`: invalidate `['/api/items']`, `getGetQueueStatsQueryKey()`, `getGetItemQueryKey(id)`.
Permissions: `canEditRisk = viewer.roles ∋ reviewer|lead`; `canEditTags = canEditRisk || row.owner?.id === viewer.id`.

- [ ] Tests: risk change shows the new tier before the server answers; `rolls back and toasts the server message
      on error` (PATCH → 403 `{code:'not_permitted', message:'Only reviewers can change risk tier.'}`); marketer
      sees risk as plain badge (no picker); tags editor adds a tag on Enter and removes with its × button.
- [ ] Implement (RAC `Select` for risk, RAC `DialogTrigger`+`Popover` with a `TextField` for tags); commit.

### Task 5: Filter bar, view tabs, saved views, stats strip

**Files:** Create `FilterBar.tsx`, `ViewBar.tsx`, `StatsStrip.tsx` + tests.

**Interfaces — produces:**
- `FilterBar({ search, onSearch })`: search field (`q`, debounced 250ms), chips: Status, Risk, Product, Channel,
  Assignee (Me / Unassigned / people from `useListUsers({ role: 'reviewer' })`), Partner (`useListPartners`),
  Open findings (Has open findings / None), Re-review reason; each chip is a RAC `MenuTrigger` with a
  multi-select `Menu`; an active chip reads `Status: In review, Submitted`; "Clear filters" when any set; Sort menu.
- `ViewBar({ search, onSearch, columns })`: built-ins + saved views as a RAC `ToggleButtonGroup`-like tab row;
  "Modified" marker; "Save view" (`useCreateSavedView`, name dialog), delete on saved views
  (`useDeleteSavedView`); views fail → inline "Couldn't load saved views" + Retry, built-ins still work.
- `StatsStrip({ onPick })`: `useGetQueueStats`; figures: In queue (`open`), Mine, Unassigned, Waiting >3 days,
  Re-review; each a button that applies its view; skeleton while loading; error → "Stats unavailable" + Retry.

- [ ] Tests: picking Status → In review sets `status=['in_review']`; clearing removes all filter keys but keeps
      layout; active built-in is `aria-pressed`; adding a filter shows "Modified"; saving posts `SavedViewIn`
      with current filters, sort, and visible columns; stats show real numbers from the handler; stats 500
      shows the inline error while the rest renders.
- [ ] Implement; commit.

### Task 6: Keyboard model and shortcuts help

**Files:** Create `keyboard.ts`, `keyboard.test.ts`, `ShortcutsDialog.tsx`.

**Interfaces — produces:** `queueKeyAction(e: { key, target, metaKey, ctrlKey, altKey }): QueueKeyAction | null`,
`QueueKeyAction = 'next' | 'prev' | 'open' | 'review' | 'select' | 'help' | 'close'`; `j/ArrowDown`,
`k/ArrowUp`, `Enter`, `o`, `x`, `?`, `Escape`. `SHORTCUTS` list used by the dialog.

- [ ] Tests: each key maps; modifiers return null; `ignores keys from editable targets` (input, textarea,
      `[contenteditable]`, `[role=combobox]`, but Escape still closes from inside the drawer).
- [ ] Implement; commit.

### Task 7: Bulk actions

**Files:** Create `BulkBar.tsx`, `BulkBar.test.tsx`.

**Interfaces — produces:** `BulkBar({ selectedIds: number[], rows, onClear, onSelectionChange })`. Lead/admin:
"Assign…" (menu of reviewers + "Unassigned") → `useBulkAssignItems`; lead + any selected `needs_rereview`:
"Fast-track approve…" (reason dialog) → `useBulkFastTrackApprove`. Reviewers without lead see the count and
Clear only. Result toast: `Assigned 4 items to Dana` or `Assigned 3 · 1 skipped: <message>`.

- [ ] Tests: `keeps skipped items selected and reports them`; reviewer sees no Assign; fast-track hidden when no
      re-review item is selected; 501 shows the server message.
- [ ] Implement; commit.

### Task 8: Preview drawer

**Files:** Create `PreviewDrawer.tsx`, `PreviewDrawer.test.tsx`, `reviewPath.ts`.

**Interfaces — produces:** `PreviewDrawer({ itemId, onClose, onOpenReview })`. `useGetItem(itemId)` +
`useListFindings(itemId)`: header (key, title, status), facts (product, channel, partner, owner, assignee,
round, version, submitted, run dates, markets, risk), open findings by severity (`2 blocking · 1 warning`, or
"No open findings"), latest decision (outcome, approver, when, reason), notes (editable via `useItemPatch` when
permitted), tags; primary "Open review" (`reviewPath(id) = '/items/' + id`). Loading skeleton matches layout;
404 → "CP-… no longer exists"; error → message + Retry.

- [ ] Tests: renders facts and `2 blocking · 1 warning` from fixtures (only `state=open` counted); latest decision
      line; "Open review" calls `onOpenReview(id)`; Escape calls `onClose`.
- [ ] Implement; commit.

### Task 9: Board

**Files:** Create `Board.tsx`, `Board.test.tsx`.

**Interfaces — produces:** `Board({ search, onOpen })`. Two list queries: queue-side statuses
`[submitted, in_review, changes_requested, needs_rereview]` (explicit — `changes_requested` isn't a queue status)
and `{ status: [approved], approved_within_days: 14 }`, both with the filter bar's other filters; columns
Submitted · In review · Changes requested · Needs re-review · Approved (14 days). Card: key, title, age, open
findings, partner, assignee. RAC `GridList` per column with `useDragAndDrop`: only Submitted cards are
draggable; only In review accepts, and only from Submitted; drop → `useClaimItem` → toast + invalidate; card
action (click/Enter) → `onOpen(id)`. Each column shows "Showing 50 · more in the table" when a page is full.

- [ ] Tests: cards land in their status columns; approved column passes `approved_within_days=14`; claim failure
      (501) toasts the server message; card press opens.
- [ ] Implement; commit.

### Task 10: Queue page, route, shell wiring

**Files:** Rewrite `features/queue/QueuePage.tsx`; modify `routes/index.tsx` (`validateSearch:
queueSearchSchema`, `search.middlewares: [stripSearchParams(DEFAULT_SEARCH-ish defaults)]`),
`routes/__root.tsx` (`SessionGate`), `ui/layout/Viewer.tsx` (Viewer = `{ id, name, email, roles }`, no demo),
`ui/layout/UserMenu.tsx` (sign out), create `ui/layout/SessionGate.tsx`, `ui/layout/SignIn.tsx`; update
`AppShell.test.tsx`, `AppShell.browser.test.tsx`, `QueuePage.browser.test.tsx`; `e2e/shell.spec.ts` stubs.

- QueuePage composes StatsStrip, ViewBar, FilterBar, layout toggle (Table/Board), BulkBar, QueueTable or Board,
  PreviewDrawer, ShortcutsDialog; handles `queueKeyAction` on the table region; states: loading skeleton
  (`SkeletonTable` with the visible columns' widths), empty per view (My queue: "Nothing assigned to you" +
  `N unassigned items` + "Show unassigned"; filters: "No items match these filters" + "Clear filters"),
  error ("Couldn't load the queue. <message>" + Retry), partial (rows shown + inline page error).
- SessionGate: `useGetMe`; loading → shell skeleton; 401 → `SignIn`; other error → one-line error + Retry; ok →
  `ViewerProvider` from `effective_roles`.

- [ ] Tests: QueuePage empty My queue copy uses `stats.unassigned`; j/k/Enter/x/o drive the table (browser test:
      real focus, `o` pushes `/items/7`); SessionGate shows SignIn on 401 and the shell after sign-in; nav
      follows `effective_roles`.
- [ ] Implement; commit.

### Task 11: E2E, screenshots, UI review, report

**Files:** Create `e2e/queue.spec.ts`, `e2e/fixtures/queue.ts`, `e2e/screenshots.spec.ts` (tagged, skipped
unless `SCREENSHOTS=1`); `docs/plan/reviews/ui/queue/*.png`, `docs/plan/reviews/ui-queue.md`,
`docs/plan/reports/queue.md`.

- [ ] e2e: table loads with stubs, filter chip updates URL, drawer opens on Enter, board toggle, sign-in on 401.
- [ ] Screenshots at 1440×900 and 1280×800: data, loading, empty, error, partial, drawer, board, filters open,
      bulk selection, shortcuts dialog, sign-in.
- [ ] Fresh UI-reviewer subagent with screenshots + spec §5 + the make-interfaces-feel-better skill; fix valid
      findings; re-shoot.
- [ ] All gates; report; PR.
