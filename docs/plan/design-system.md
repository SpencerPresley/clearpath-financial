# Design system, icon registry, and app shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship the ClearPath tokens, icon registry, core status/primitive components, and the app shell that
every later frontend workstream (H queue, I, J) builds on, plus a `/dev/design` gallery for review.

**Architecture:** All visual decisions live in `src/theme/theme.css` as Tailwind v4 `@theme` tokens and
`app-*` component classes; daisyUI's theme is aliased onto the same values. Icons go through one registry
(`src/ui/icons.ts`) and one `<Icon>` component. Components in `src/ui/` wrap React Aria Components for
anything interactive. Lint and unit tests enforce the three invariants: no raw palette colors, no Phosphor
imports outside the registry, no two registry keys sharing a glyph.

**Tech Stack:** React 19, TanStack Router (file routes), Tailwind v4 + daisyUI 5, React Aria Components
1.22.1, `@phosphor-icons/react` 2.1.10, `@fontsource-variable/inter` + `@fontsource-variable/jetbrains-mono`,
Vitest (jsdom + browser), Playwright.

**Spec:** `docs/spec.md` §1, §5 (binding), §8.4; `docs/product-spec.md` (Roles, Screens, Status machine);
`backend/core/domain.py` (enum values).

**Execution:** native, in one session. Every task consumes the same two shared interfaces (`theme.css`
tokens, `icons.ts` keys); per-task subagents would each re-derive them and drift. One fresh UI reviewer runs
at the end (Task 9) on screenshots, per §8.4.

## Global Constraints

- Color meaning (spec §5.2): brand navy = chrome, primary action, focus, never a status. Neutral slate =
  draft, submitted, expired, withdrawn, disabled. Info blue = in review. Warning amber = changes requested,
  warning findings. Success green = approved. Error red = rejected, blocking findings, destructive actions.
  Alert red-orange = needs re-review, drift.
- The warm brand accent appears only in the wordmark; it is never a UI state color (it would otherwise sit
  next to amber and red-orange). _Revised after UI review: no warm accent at all; see the report._
- Every badge = icon + label. Color is never the only signal. WCAG 2.2 AA: text pairs >= 4.5:1, focus ring
  and icons-as-sole-signal >= 3:1.
- Status labels (exact): Draft, Submitted, In review, Changes requested, Approved, Rejected, Re-review,
  Expired, Withdrawn. Source labels: code -> "Code check", llm -> "AI suggestion", human -> "Checklist".
  Severity: "Blocking", "Warning". Risk tier: "High risk", "Medium risk", "Low risk".
- Copy (§5.4): short, domain-native, glossary terms only (Item, Version, Round, Finding, Decision,
  Placement, Offer terms, Partner, Re-review). No "Violation", no celebratory copy, no emoji.
- Anti-patterns (§5.6): no sparkle/wand for AI, no gradients/glass, no card-and-shadow everything, no
  centered hero empty states, radii <= 6px, shadows only on overlays.
- Phosphor 2.x: import `XxxIcon` names (bare names are deprecated). Only `src/ui/icons.ts` imports Phosphor.
- RAC Toast is `UNSTABLE_*` in 1.22.1: only `src/ui/toast.tsx` imports it.
- Don't touch `frontend/openapi/**` or `frontend/src/api/**`.
- Domain enums are mirrored in `src/ui/domain.ts` from `backend/core/domain.py` until the generated
  contract exports them.

## Review Focus

1. A role with no access to a section (marketer) must not see Queue/Offer terms/Partners/Metrics/Import;
   a multi-role user sees the union, in a stable order. Test: `navSectionsFor(['marketer'])` and
   `navSectionsFor(['reviewer','admin'])` in Task 7.
2. Collapsed nav must still name every item to AT and sighted users (tooltip + aria-label), and the
   collapse state survives reload. Test: AppShell browser test in Task 7.
3. `RelativeAge` with a future timestamp (clock skew) or invalid string must not render "-3d" or "NaN".
   Test: `RelativeAge.test.tsx` cases "future clamps to 'now'" and "invalid date renders an em dash" in Task 5.
4. `ItemKey` copy when the Clipboard API rejects (insecure context, permission): no unhandled rejection,
   user sees "Couldn't copy". Test in Task 5.
5. API down must be prominent, API up must be quiet, and "checking" must not flash a badge on every load.
   Test: `ApiStatusBadge.test.tsx` + e2e 503 case in Task 7.

---

### Task 1: Tokens, fonts, contrast test, palette lint

**Files:**

- Modify: `frontend/src/theme/theme.css`, `frontend/src/main.tsx` (font imports), `frontend/eslint.config.ts`,
  `frontend/package.json`
- Create: `frontend/src/theme/contrast.ts` (oklch -> sRGB -> WCAG ratio), `frontend/src/theme/contrast.test.ts`,
  `frontend/src/theme/paletteLint.test.ts`

**Interfaces — Produces:**

- Token families in `@theme` (utilities `bg-*`, `text-*`, `border-*`): `status-neutral`, `status-info`,
  `status-warning`, `status-success`, `status-error`, `status-alert`, each with `-soft` (badge bg),
  `-soft-content` (badge text/icon), `-line` (badge border), plus solid `<fam>` / `<fam>-content` for
  daisyUI aliases (info/success/warning/error) and `alert`.
- `--color-brand-accent` (wordmark only), `--color-focus` (focus ring), `--font-sans: 'Inter Variable'`,
  `--font-mono: 'JetBrains Mono Variable'`, radius reset to `--radius-sm: 3px`, `--radius-md: 4px`,
  `--radius-lg: 6px`; shadow reset to `--shadow-overlay` only; layout tokens `--app-topbar-h: 3rem`,
  `--app-nav-w: 13.5rem`, `--app-nav-w-collapsed: 3.25rem`, `--app-row-h: 2.25rem`.
- `contrastRatio(fg: string, bg: string): number` accepting `oklch(L% C H)` strings.
- ESLint rule `clearpath/no-raw-palette` (inline plugin in `eslint.config.ts`, also exported as
  `noRawPaletteRule`).

- [ ] Step 1: `contrast.test.ts`: `contrastRatio('oklch(0% 0 0)', 'oklch(100% 0 0)')` ≈ 21; then parse
      theme.css, for every pair in `PAIRS` (each `-content` on its base, each `-soft-content` on its `-soft`
      and on `base-100`, `base-content` on base-100/200, muted text on base-100/200, primary-content on
      primary, focus on base-100 (>= 3)) assert ratio >= 4.5. Print a table (used in the report).
- [ ] Step 2: run, fails (no module). Step 3: implement `contrast.ts` and the tokens. Step 4: pass.
- [ ] Step 5: `paletteLint.test.ts`: `Linter` with `noRawPaletteRule` reports on `className="bg-blue-500"`,
      ``cx(`hover:text-red-600`)``, `"bg-[#fff]"`; does not report on `bg-neutral`, `text-base-content`,
      `bg-status-alert-soft`. Fail, implement, pass.
- [ ] Step 6: wire fonts (`@fontsource-variable/*` imports in main.tsx), `antialiased`, `tabular-nums` on
      `.app-figure`. `npm run lint && npm run typecheck && npm run test:run`. Commit.

### Task 2: Domain mirror + icon registry

**Files:** Create `frontend/src/ui/domain.ts`, `frontend/src/ui/icons.ts`, `frontend/src/ui/Icon.tsx`,
`frontend/src/ui/icons.test.ts`, `frontend/src/ui/Icon.test.tsx`. Modify `frontend/eslint.config.ts`.

**Interfaces — Produces:**

- `ITEM_STATUSES`, `SEVERITIES`, `FINDING_SOURCES`, `RISK_TIERS`, `ROLES` as `readonly` tuples;
  types `ItemStatus`, `Severity`, `FindingSource`, `RiskTier`, `Role`.
- `icons: Record<IconKey, { glyph: Icon; weight: IconWeight }>`, `type IconKey`, `SHARED_GLYPHS`
  (allowlist: `readonly { keys: readonly IconKey[]; why: string }[]`).
- `<Icon name: IconKey; size?: number (default 16); label?: string; weight?: IconWeight; className? />` —
  `aria-hidden` unless `label`, then `role="img"` + `aria-label`.

- [ ] Step 1: `icons.test.ts`: every glyph reference is unique except groups in `SHARED_GLYPHS`; every
      allowlist entry names >= 2 keys that really share; `source.code` weight `fill`, `source.ai` `regular`;
      every `ItemStatus` has `status.<value>`; every severity has `severity.<value>`. Fail, implement, pass.
- [ ] Step 2: `no-restricted-imports` for `@phosphor-icons/react` and `@phosphor-icons/react/*` with
      `files: ['src/ui/icons.ts']` override off. Verify lint fails on a scratch import. Commit.

Glyph discriminator: statuses are enclosed glyphs (`CheckCircleIcon`), actions are bare (`CheckIcon`),
so approve/approved don't collide. Full table goes in the report.

### Task 3: Badges (StatusBadge, SeverityBadge, SourceTag, RiskTierBadge)

**Files:** Create `frontend/src/ui/badges.tsx` + `frontend/src/ui/badges.test.tsx`; classes in theme.css.

**Interfaces — Produces:** `STATUS_META: Record<ItemStatus, { label; tone: Tone; icon: IconKey }>`;
`<StatusBadge status: ItemStatus; compact?: boolean />` (compact = icon only + tooltip + aria-label, for
dense cells); `<SeverityBadge severity: Severity />`; `<SourceTag source: FindingSource />`;
`<RiskTierBadge tier: RiskTier />`; `type Tone = 'neutral'|'info'|'warning'|'success'|'error'|'alert'`.

- [ ] Tests: for each status, label text exact, an svg present, `data-tone` matches the §5.2 table;
      `SourceTag source="llm"` reads "AI suggestion" with regular-weight icon; risk tier is neutral tone (risk
      is not a status color). Fail, implement, pass, commit.

### Task 4: Buttons, IconButton, Tooltip, Kbd

**Files:** Create `frontend/src/ui/Button.tsx`, `IconButton.tsx`, `Tooltip.tsx`, `Kbd.tsx` + tests.

**Interfaces — Produces:** `<Button variant?: 'primary'|'secondary'|'ghost'|'danger' (default secondary);
size?: 'sm'|'md'; icon?: IconKey; ...RAC ButtonProps>`; `<IconButton icon: IconKey; 'aria-label': string
(required by type); tooltip?: boolean (default true); variant?; size? >`; `<Tooltip content: ReactNode;
children: ReactElement (focusable); placement? />`; `<Kbd keys: readonly string[] />`.

- [ ] Tests: button fires `onPress`, disabled doesn't, variant class applied; IconButton has accessible name
      and shows tooltip on focus; Kbd renders `<kbd>` per key. Fail, implement, pass, commit.

### Task 5: ItemKey, RelativeAge, toast host

**Files:** Create `frontend/src/ui/ItemKey.tsx`, `RelativeAge.tsx`, `toast.tsx` + tests.

**Interfaces — Produces:** `<ItemKey value: string /* "CP-1042" */; copyable?: boolean (default true) />`;
`formatAge(at: Date, now: Date): string` ("now", "12m", "5h", "3d", "6w", "4mo", "2y");
`<RelativeAge at: string | Date; now?: Date />` (`<time dateTime>`, absolute time in tooltip and sr text);
`toast.show({ title: string; description?: string; tone?: 'neutral'|'error' }, timeout?)`, `<ToastHost />`.

- [ ] Tests: ItemKey copies on press and announces "Copied"; on clipboard rejection shows "Couldn't copy";
      formatAge boundaries (59s -> now, 60s -> 1m, 23h -> 23h, 24h -> 1d, 13d -> 13d, 14d -> 2w);
      future -> "now"; invalid -> "—"; toast.show renders in a `region` and closes via its close button.

### Task 6: EmptyState, Skeleton primitives

**Files:** Create `frontend/src/ui/EmptyState.tsx`, `Skeleton.tsx` + tests.

**Interfaces — Produces:** `<EmptyState icon: IconKey; title: string; children? (detail); action?: ReactNode />`
(left-aligned, inline in the data region, not a centered hero); `<SkeletonText width?: string />`,
`<SkeletonBadge />`, `<SkeletonTable rows: number; columns: readonly string[] (width per column) />`
(rows use `--app-row-h`, `aria-busy`, single sr "Loading" label).

### Task 7: App shell

**Files:** Rewrite `frontend/src/ui/layout/AppShell.tsx`; create `frontend/src/ui/layout/nav.ts`,
`Viewer.tsx`, `UserMenu.tsx`, `SearchField.tsx`, `nav.test.ts`, `AppShell.test.tsx`,
`AppShell.browser.test.tsx`; modify `frontend/src/features/system/ApiStatusBadge.tsx` (+ test),
`frontend/src/routes/__root.tsx`, `frontend/e2e/shell.spec.ts`.

**Interfaces — Produces:** `NAV_SECTIONS: readonly NavSection[]` with `{ id; label; icon: IconKey;
roles: readonly Role[]; to?: '/' }`; `navSectionsFor(roles: readonly Role[]): NavSection[]`;
`ViewerProvider`, `useViewer(): { name: string; roles: readonly Role[]; isDemo: boolean }` (default: all
roles, `isDemo: true` until `/api/me` exists); `<AppShell />`.

Section roles (product-spec Screens): Queue = reviewer, lead; My submissions, New submission = marketer;
Library, Outbox = everyone; Offer terms, Partners, Metrics = lead; Import = admin. Sections without a
route render disabled with tooltip "Not built yet".

- [ ] Tests: nav filtering (Review Focus 1); shell renders wordmark, disabled search with "Search ships
      later" hint, user menu opens with RAC; API status quiet when ok (no visible badge text), prominent alert
      when down; browser test: collapse toggles width, persists in localStorage, Tab shows a focus ring with
      non-zero outline width. e2e: shell + 503 case.

### Task 8: Design gallery

**Files:** Create `frontend/src/routes/dev/design.tsx` (thin), `frontend/src/ui/gallery/DesignGallery.tsx`.
Not in `NAV_SECTIONS`. Sections: color tokens (with live contrast ratio), type, spacing/radius/shadow,
icons (every registry key), every badge value, buttons in every variant x state, ItemKey, RelativeAge,
Tooltip, Kbd, toasts, EmptyState, skeletons. Test: renders every `ItemStatus` label.

### Task 9: UI review and gates

- [ ] Run all gates. Screenshot shell + gallery at 1440x900 and 1280x800 into
      `docs/plan/reviews/ui/design-system/`. Dispatch one fresh UI reviewer with the screenshots and spec §5.
      Fix valid findings; record in `docs/plan/reviews/ui-design-system.md`. Report to
      `docs/plan/reports/design-system.md`. PR "Design system, icon registry, and app shell".
