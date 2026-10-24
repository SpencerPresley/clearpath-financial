# Report: design system, icon registry, and app shell (workstream H, part 1)

Part of #9. Branch `wsH/design-system`. Plan: `docs/plan/design-system.md`. UI review:
`docs/plan/reviews/ui-design-system.md`, screenshots in `docs/plan/reviews/ui/design-system/`.

Execution: native (one session). Every task consumed the same two interfaces (`theme.css` tokens and the
`icons.ts` keys), so per-task subagents would each have re-derived them; one fresh UI reviewer ran at the
end on screenshots per spec §8.4.

Note: issue #9 names the plan/report `frontend-queue.md`; this half of H uses `design-system.md` per the
task brief. The queue table half should use `frontend-queue.md`.

## Tokens

All in `frontend/src/theme/theme.css`. Tailwind's palette, radii, and shadows are reset (`--color-*`,
`--radius-*`, `--shadow-*: initial`), so only ClearPath tokens compile. daisyUI's `info/success/warning/
error` are `var()` aliases of the status tokens, so `btn-error` and `app-badge[data-tone=error]` can't drift.

| Family | Tokens | Job (spec §5.2) |
|---|---|---|
| Brand | `primary` navy `oklch(30% 0.085 262)`, `primary-hover`, `brand-muted`, `brand-field`, `brand-hover`, `nav-active` (grey + navy bar), `focus` `oklch(38% 0.11 262)`, `focus-on-brand` | Chrome, primary action, focus. No warm accent (see below). |
| Surfaces | `base-100` content, `base-200` canvas, `base-300` rules, `base-content`, `muted`, `hover` (translucent), `skeleton` | |
| Status tones x6 | `status-{neutral,info,warning,success,error,alert}` each with `-content`, `-soft`, `-soft-content`, `-line` | neutral = draft/submitted/expired/withdrawn; info = in review; warning = changes requested, warning findings; success = approved; error = rejected, blocking, destructive; alert = re-review, drift |
| Type | `--font-sans` Inter Variable, `--font-mono` JetBrains Mono Variable (both self-hosted via `@fontsource-variable/*`), `text-ui` 13/20, `text-meta` 12/16; figures use `tabular-nums` | |
| Radius | `xs` 2px, `sm` 3px, `md` 4px, `lg` 6px (ceiling) | |
| Shadow | `shadow-overlay` only (menus, popovers, tooltips, toasts) | Surfaces sit flat on rules (§5.6) |
| Layout | `topbar` 48px, `nav` 216px / `nav-collapsed` 52px, `row` 36px | Shared with the queue table and skeletons |

Decisions (judgment, with the mechanism):
- **Alert badges are the only solid-filled status badge.** Alert (hue 42) and error (hue 26) are close in
  hue on a soft fill; making alert solid separates them by fill and glyph, and matches "act now".
- **No warm brand accent (deviation from the brief).** The brief asked for navy plus one warm accent. Every
  warm hue is already a status in spec §5.2 (error 26, alert 42, warning 80); the first pass confined a
  gold accent to the wordmark and the UI reviewer still flagged it as warning amber in a warning-sign shape
  (`brand-accent` 84% 0.1 82 vs `status-warning-line` 85% 0.1 82). Spec won: the wordmark mark is an
  outlined square in `primary-content`, and daisyUI's required `accent` aliases navy. Spencer's call if he
  wants a warm brand color back; the cost is one hue that can't be told from a status.
- **Risk tier takes no status color** (outline badge + direction glyph). It's an attribute, not a workflow
  state; red "High" would borrow error's meaning.
- **13px UI text on `body`, not `html`.** On `html` it rescaled every rem (the browser test caught the nav
  at 175.5px instead of 216px).

### Contrast (WCAG 2.2 AA), enforced by `src/theme/contrast.test.ts`

The test parses `theme.css`, resolves `var()` aliases, converts OKLCH to sRGB, asserts every token is in
gamut (so the computed ratio is what renders), and checks each pair. Text >= 4.5:1, non-text >= 3:1.
Print with `PRINT_CONTRAST=1 npx vitest run --project unit src/theme/contrast.test.ts --silent=false`.

| Foreground | Background | Ratio | Min |
|---|---|---|---|
| base-content | base-100 | 15.77 | 4.5 |
| base-content | base-200 | 14.67 | 4.5 |
| muted | base-100 | 6.72 | 4.5 |
| muted | base-200 | 6.26 | 4.5 |
| primary-content | primary | 13.19 | 4.5 |
| primary-content | primary-hover | 10.10 | 4.5 |
| primary-content | brand-field | 10.05 | 4.5 |
| brand-muted | brand-field | 5.61 | 4.5 |
| status-error-content | status-error-hover | 7.78 | 4.5 |
| muted | base-300 | 5.30 | 3 |
| brand-muted | primary | 7.37 | 4.5 |
| primary | base-100 | 13.57 | 4.5 |
| primary | nav-active | 11.55 | 4.5 |
| secondary-content | secondary | 6.82 | 4.5 |
| neutral-content | neutral | 14.02 | 4.5 |
| focus | base-100 | 10.02 | 3 |
| focus | base-200 | 9.32 | 3 |
| focus-on-brand | primary | 13.19 | 3 |
| status-neutral-content | status-neutral | 6.35 | 4.5 |
| status-neutral-soft-content | status-neutral-soft | 8.30 | 4.5 |
| status-neutral-soft-content | base-100 | 9.46 | 4.5 |
| status-info-content | status-info | 5.76 | 4.5 |
| status-info-soft-content | status-info-soft | 7.17 | 4.5 |
| status-info-soft-content | base-100 | 8.04 | 4.5 |
| status-warning-content | status-warning | 8.36 | 4.5 |
| status-warning-soft-content | status-warning-soft | 7.11 | 4.5 |
| status-warning-soft-content | base-100 | 7.87 | 4.5 |
| status-success-content | status-success | 5.52 | 4.5 |
| status-success-soft-content | status-success-soft | 7.48 | 4.5 |
| status-success-soft-content | base-100 | 8.30 | 4.5 |
| status-error-content | status-error | 6.07 | 4.5 |
| status-error-soft-content | status-error-soft | 7.08 | 4.5 |
| status-error-soft-content | base-100 | 8.02 | 4.5 |
| status-alert-content | status-alert | 5.47 | 4.5 |
| status-alert-soft-content | status-alert-soft | 6.22 | 4.5 |
| status-alert-soft-content | base-100 | 7.13 | 4.5 |
| info-content | info | 5.76 | 4.5 |
| success-content | success | 5.52 | 4.5 |
| warning-content | warning | 8.36 | 4.5 |
| error-content | error | 6.07 | 4.5 |

## Lint rules

- `clearpath/no-raw-palette` (`src/theme/noRawPalette.ts`, wired in `eslint.config.ts` for `src/**/*.tsx`):
  every string literal and template chunk, not just `className=`, so `cx()` arguments are covered. Flags
  palette utilities with a numeric shade (`bg-blue-500`, `hover:text-red-600/50`; the 26 names were checked
  against the installed Tailwind's `theme.css`), arbitrary colors (`bg-[#fff]`, `text-[oklch(...)]`), and
  radius/shadow sizes the reset drops (`rounded-2xl`, `shadow-lg`). `bg-neutral` (daisyUI token) stays legal.
  14 RuleTester-style cases in `noRawPalette.test.ts`.
- `no-restricted-imports`: `@phosphor-icons/*` and `@phosphor-icons/react/*` banned in `src/**` except
  `src/ui/icons.ts`. Probed with a scratch file: both the root and a `dist/csr/X` deep import fail.

## Icon registry (`src/ui/icons.ts`)

Phosphor 2.1.10 (`XxxIcon` exports; bare names are deprecated in 2.x). Rule: states are enclosed glyphs,
actions bare, so Approved/Approve don't collide. `icons.test.ts` fails on any shared glyph (by component
reference) outside `SHARED_GLYPHS`; mutation-checked by pointing `action.close` at `XCircleIcon` (test
failed naming `status.rejected` + `action.close`).

| Key | Phosphor glyph | Weight |
|---|---|---|
| `status.draft` | NotePencil | regular |
| `status.submitted` | PaperPlaneTilt | regular |
| `status.in_review` | Eye | regular |
| `status.changes_requested` | ArrowUUpLeft | regular |
| `status.approved` | CheckCircle | regular |
| `status.rejected` | XCircle | regular |
| `status.needs_rereview` | ArrowsCounterClockwise | bold |
| `status.expired` | CalendarX | regular |
| `status.withdrawn` | MinusCircle | regular |
| `severity.blocking` | WarningOctagon | fill |
| `severity.warning` | Warning | fill |
| `source.code` | Ruler | fill |
| `source.ai` | Cpu | regular |
| `source.human` | ListChecks | regular |
| `risk.high` | CaretDoubleUp | bold |
| `risk.medium` | Equals | bold |
| `risk.low` | CaretDoubleDown | bold |
| `entity.item` | FileText | regular |
| `entity.version` | Stack | regular |
| `entity.partner` | Handshake | regular |
| `entity.terms` | Percent | regular |
| `entity.placement` | MapPin | regular |
| `entity.decision` | Gavel | regular |
| `entity.finding` | Flag | regular |
| `action.approve` | Check | bold |
| `action.request_changes` | ArrowBendUpLeft | regular |
| `action.reject` | Prohibit | regular |
| `action.assign` | UserPlus | regular |
| `action.comment` | ChatCircle | regular |
| `action.export` | Export | regular |
| `action.import` | TrayArrowDown | regular |
| `action.search` | MagnifyingGlass | regular |
| `action.filter` | Funnel | regular |
| `action.sort` | SortAscending | regular |
| `action.copy` | Copy | regular |
| `action.edit` | PencilSimple | regular |
| `action.close` | X | regular |
| `action.more` | DotsThree | bold |
| `action.expand` | CaretDown | regular |
| `action.open_external` | ArrowSquareOut | regular |
| `action.toggle_nav` | SidebarSimple | regular |
| `action.sign_out` | SignOut | regular |
| `nav.queue` | Tray | regular |
| `nav.my_submissions` | FolderSimpleUser | regular |
| `nav.new_submission` | FilePlus | regular |
| `nav.library` | Books | regular |
| `nav.offer_terms` | Percent | regular |
| `nav.partners` | Handshake | regular |
| `nav.metrics` | ChartLine | regular |
| `nav.import` | TrayArrowDown | regular |
| `nav.outbox` | EnvelopeSimple | regular |
| `nav.user` | UserCircle | regular |
| `nav.notifications` | Bell | regular |
| `notify.mention` | At | regular |
| `notify.expiring` | ClockCountdown | regular |
| `action.mark_all_read` | Checks | regular |
| `system.api_offline` | Plugs | bold |
| `feedback.error` | WarningCircle | regular |
| `feedback.info` | Info | regular |

55 keys, 52 distinct glyphs.

Allowlisted shares (`SHARED_GLYPHS`, each with its reason in code): `entity.terms` = `nav.offer_terms`,
`entity.partner` = `nav.partners`, `action.import` = `nav.import`.

## Components (`src/ui/`)

| Component | Props | Notes |
|---|---|---|
| `Icon` | `name: IconKey`, `size?=16`, `weight?`, `label?`, `className?` | `aria-hidden` unless `label`, then `role="img"` |
| `StatusBadge` | `status: ItemStatus` | Labels: Draft, Submitted, In review, Changes requested, Approved, Rejected, Re-review, Expired, Withdrawn; `STATUS_META` exported |
| `SeverityBadge` | `severity: 'blocking' \| 'warning'` | error / warning tone, filled glyphs |
| `SourceTag` | `source: 'code' \| 'llm' \| 'human'` | "Code check" (fill), "AI suggestion" (regular), "Checklist"; no color |
| `RiskTierBadge` | `tier: 'high' \| 'medium' \| 'low'` | "High risk" etc., outline, no status color |
| `Button` | RAC `ButtonProps` + `variant?: primary\|secondary\|ghost\|danger` (default secondary), `size?: sm\|md`, `icon?: IconKey` | 32px / 28px; scale 0.96 on press |
| `IconButton` | RAC `ButtonProps` + `icon`, `'aria-label'` (required by type), `tooltip?=true`, `variant?=ghost`, `size?` | aria-label doubles as tooltip |
| `Tooltip` | `content`, `children` (focusable), `placement?='top'`, `delay?=500` | RAC `TooltipTrigger` |
| `Kbd` | `keys: readonly string[]` | nested `<kbd>` |
| `ItemKey` | `value: string`, `copyable?=true` | mono; copy button on hover/focus; `role=status` says "Copied" / "Couldn't copy" |
| `RelativeAge` | `at: string \| Date`, `now?: Date` | `now`, `12m`, `5h`, `3d`, `2w`, `4mo`, `1y`; future clamps to `now`; invalid renders an em dash; absolute time as tooltip and accessible name |
| `EmptyState` | `icon: IconKey`, `title`, `children?` (detail), `action?` | left-aligned, inline (not a hero) |
| `SkeletonText` / `SkeletonBadge` / `SkeletonTable` | `width?` / none / `rows`, `columns: readonly string[]`, `label?` | rows use the 36px row token; one spoken label |
| `ToastHost`, `showToast(content, timeout?)`, `toastQueue` | `{ title, description?, tone?: 'neutral' \| 'error' }` | errors persist until dismissed; only file importing RAC `UNSTABLE_Toast*` |
| `domain.ts` | `ITEM_STATUSES`, `SEVERITIES`, `FINDING_SOURCES`, `RISK_TIERS`, `ROLES` + types | mirrors `backend/core/domain.py` until the generated contract exports them |

Shell (`src/ui/layout/`): `AppShell`, `nav.ts` (`NAV_SECTIONS`, `navSectionsFor(roles)`, `navGroupsFor`),
`NavLink` (`createLink(RAC Link)`, the TanStack-documented pattern), `Viewer.tsx` (`ViewerProvider`,
`useViewer`, `DEMO_VIEWER`), `UserMenu`, `SearchField`. Gallery: `src/ui/gallery/DesignGallery.tsx`
routed at `src/routes/dev/design.tsx`, absent from `NAV_SECTIONS`.

## App shell behavior

- Topbar (48px navy): nav toggle, wordmark (links to `/`), disabled search ("Search (soon)"), API status,
  account button.
- API status: invisible while the first check runs and when healthy (sr-only text, no tab stop); when
  `/api/health` fails or reports non-ok, a soft-error chip "Can't reach server · changes won't save" inside
  `role="alert"`. Rechecks every 30s (`refetchInterval`).
- Nav: grouped Work / Reference / Operations, filtered by `useViewer().roles` (union; stable order).
  Queue = reviewer, lead; My submissions, New submission = marketer; Library, Outbox = everyone; Offer
  terms, Partners, Metrics = lead; Import = admin. Only Queue has a route; the rest are focusable
  `role="link" aria-disabled` items marked "Soon" (no placeholder pages). Collapses to a 52px rail with
  tooltips; choice persists in `localStorage` (`clearpath.nav.collapsed`, guarded for blocked storage).
- Viewer: no session endpoint exists, so the default is `DEMO_VIEWER` (all roles, `isDemo`), and the
  account panel says "No sign-in yet". The root route should wrap the app in `ViewerProvider` once
  `/api/me` lands.
- Skip link to `#main`; one focus ring (2px, navy on light, white on the topbar).

## UI review

One fresh reviewer, screenshots at 1440x900 and 1280x800 + spec §5. Result: 0 blockers, 8 should-fix
(all fixed), 8 nits (6 fixed, 2 declined with reasons). Full table: `docs/plan/reviews/ui-design-system.md`.
The ones that changed the design:
- `source.code` ShieldCheck -> filled Ruler (a check glyph on a flagged problem said "passed").
- `feedback.error` filled -> outline (indistinguishable from `severity.blocking` at 16px; the identity
  test can't catch look-alikes, so the registry header now states the silhouette rule).
- Warm accent removed (above); selected-nav tint de-blued (it read as "In review").
- API status: healthy glyph removed (looked like a sparkle, cost a Tab stop); down chip restyled from
  button-like to badge-like and states the consequence.
- Account: popover dialog instead of a menu whose only item was a disabled "Sign out".

## Verification

Run from `frontend/` on the final commit:

```
npm run lint            -> eslint . (no output, exit 0)
npm run format:check    -> All matched files use Prettier code style!
npm run typecheck       -> tsc -b (exit 0)
npm run test:run        -> Test Files 12 passed (12); Tests 145 passed (145)
npm run build           -> built (tsc -b && vite build)
npm run test:browser    -> Test Files 2 passed (2); Tests 4 passed (4)
npm run test:e2e        -> 3 passed
```

What the tests pin, beyond rendering: every token in sRGB gamut and every pair above its WCAG minimum;
the palette rule's 14 cases; no shared glyph outside the allowlist (mutation-checked); §5.2 tone per status
restated in the test; nav filtering per role incl. union and no-roles; collapse persists and keeps items
named; unbuilt items keyboard-reachable with tooltip; API quiet/prominent/pending; clipboard rejection
shows "Couldn't copy" without an unhandled rejection; age boundaries, future clamp, invalid input. Browser
tests: nav is 216px / 52px (this caught `text-ui` on `html` rescaling rem to 13px), focus ring is 2px solid
on keyboard focus, Inter Variable loaded, ages use tabular-nums. e2e: shell, API-down alert, gallery
route reachable and absent from nav.

## Files touched outside the listed ownership

- `frontend/src/features/system/ApiStatusBadge.tsx` (+ test): the brief asks to make it quiet.
- `frontend/e2e/shell.spec.ts`: asserted the old wordmark and `API: online`; now also covers API down and
  the gallery route.
- `frontend/vite.config.ts`: one line, `css.include` for `theme.css` in the unit project. Vitest replaces
  CSS imports with `""` by default, even with `?raw`, which made the contrast test see no tokens.
- `frontend/src/routeTree.gen.ts`: regenerated by the router plugin for `/dev/design`.

## Deferred and risks

- **Generated enums.** `src/ui/domain.ts` mirrors `backend/core/domain.py`; swap to generated types when
  the workstream-0 contract exports them (one file to change).
- **Viewer.** `DEMO_VIEWER` until a current-user endpoint exists; then `ViewerProvider` in the root route,
  sign-out in the account panel.
- **Nav routes.** Workstreams I/J set `to` on their `NAV_SECTIONS` entry as screens ship.
- **Compact (icon-only) status badge for dense cells** (spec §5.2a tooltip + aria-label) is not built: it
  depends on the queue table's keyboard model (RAC Table cell focus vs per-badge tab stops). Queue task.
- **RAC Toast is `UNSTABLE_*`** in react-aria-components 1.22.1. Isolated to `src/ui/toast.tsx`.
- **Bundle.** The main chunk is 671 kB minified (Vite's >500 kB warning). Phosphor tree-shakes (53
  glyphs in the bundle = 53 used) but each glyph ships all six weights: about 159 kB of raw defs. If it
  matters, a build-time step or `IconBase` with only the used weight would cut most of it; route-level
  splitting of RAC/Query is the other lever. Not done here.
- **Hit area.** Buttons are 32px / 28px, below the make-interfaces skill's 40px rule, on purpose: spec §5.3
  density, and WCAG 2.5.8 (24px) is met. The reviewer agreed.
- **Copy.** "Soon" on unbuilt sections is a demo-build artifact; it disappears as sections ship.
