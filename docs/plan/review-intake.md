# Review screen, intake, and My submissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship the reviewer's Review screen (`/items/$itemId`), the marketer's New submission (`/submit`) with
live code checks, and My submissions (`/mine`) with the resubmit flow, against the generated API client.

**Architecture:** A shared copy layer in `src/ui/copy/` (span segmentation, highlighted text, a highlighting
editor, live checks, word diff) and `src/ui/findings/` (finding summary + grouping) is consumed by three
features that never import each other: `features/review`, `features/submit`, `features/mine`. All server
state goes through the generated React Query hooks; decision gating, event sentences, and "waiting on whom"
are pure functions with unit tests. Styling is `app-*` classes in one new section of `theme.css`.

**Tech Stack:** React 19, TanStack Router (file routes, zod-validated search), Query 5, Form 1 (+ generated
zod), React Aria Components 1.22, Tailwind v4 + daisyUI, `diff` (jsdiff 9) for client-side word diff,
Vitest + MSW 3, Playwright.

**Spec:** `docs/spec.md` §1, §4.2 rulings 2–6, §4.3 Intake/Checks/Review, §5 (binding), §7, §8.4;
`docs/product-spec.md` (Review layout, New submission, My submissions, status machine); `docs/decisions.md`
(Approve-with-changes, Two kinds of file, Ergonomics); `docs/plan/reports/foundation.md` (API, conventions).

**Execution:** hybrid. Tasks 1–3 (shared layer, fixtures, theme section) native, because every screen
consumes their interfaces. Then Tasks 4–6 (marketer side) go to one subagent in its own worktree branched
from the Task 3 commit, while Tasks 7–11 (review) run natively; merge, then Tasks 12–14 (e2e, UI review,
report/PR). Parallel agents in one worktree would see each other's half-edited `theme.css` and routes.

## Global Constraints

- Color (§5.2): navy = chrome/primary action/focus, never status. Warning amber = warning findings,
  changes requested. Error red = blocking findings, reject, destructive. Alert red-orange = re-review.
  Success green = approved. Diff insert/delete use **no status color**: insert = underline + neutral tint,
  delete = strikethrough + muted text (shape, not hue).
- Finding source by shape + label: code = filled Ruler "Code check", AI = outline Cpu "AI suggestion",
  human = ListChecks "Checklist" (`SourceTag`). Span marks: code = solid underline, AI = dashed underline,
  human = dotted; blocking marks also get a tinted fill, warning marks underline only (non-color severity cue).
- Copy (§5.4): glossary terms only. AI output = "message · citation", labeled "AI suggestion". Never
  "violation", "non-compliant", "AI approved", or celebration. Errors: what happened + what to do, one line.
- The AI never approves (§7): no control labels AI output as a pass; the LLM status only blocks or unblocks
  the human Approve.
- Gates (ruling 3): Approve and Approve with edits need every current-version finding accepted or dismissed
  and the AI check not `pending|running`; `failed` allows Approve with a required override reason;
  `skipped|succeeded` don't block. Request changes and Reject don't need triage. Every decision needs a reason.
- Confirmation dialogs only for Reject and Pull (§5.7).
- Icons only via `<Icon name>` and registry keys; no Phosphor imports outside `src/ui/icons.ts`. New glyphs,
  if any, are added to the registry and must pass `icons.test.ts`.
- Features import from `api/`, `ui/`, theme classes only. Never hand-edit `src/api/generated`.
- Don't modify `routes/__root.tsx`, `routes/index.tsx`, `ui/layout/Viewer.tsx`, `features/queue/**` (H2 owns
  them now). Role gating reads `useViewer().roles`; deciding = `reviewer | lead`.
- Live checks: debounce **150 ms** (the spec's 300 ms is the end-to-end budget), stale responses dropped
  (React Query key on the input + `signal`), and a mark is drawn only if `text.slice(start, end) === quote`.
- Density: 13px UI text, 28/32px controls, radii ≤ 6px, overlays only get shadows.

## Review Focus

1. Overlapping or nested finding spans (an AI span inside a code span) → every character renders once,
   both findings stay clickable. Test in Task 1 (`segmentText` overlap cases).
2. Keyboard shortcuts while typing a dismiss reason, comment, or edited copy → letters type, no triage
   fires. Test in Task 2 (`useHotkeys` ignores editable targets) and Task 9.
3. Viewing an older version → triage and decisions are disabled and the bar says decisions apply to the
   current version. Test in Task 8.
4. Live-check response for stale text (typed after the request) → marks whose quote no longer matches are
   hidden, never mis-placed. Test in Task 1 (`visibleMarks`).
5. Emoji or other astral characters before a span (affiliate copy has them) → highlights land on the
   quoted text, not one character late. Test in Task 1 (`toUtf16Span`) and Task 8 (a fixture with 💸).
6. Submit with a partner-required channel and no partner, or a 422 from the server → the error lands on the
   field, not a toast. Test in Task 4.

---

### Task 1: Copy layer (segments, highlighted text, editor, live checks, diff)

**Files:**
- Create: `frontend/src/ui/copy/segments.ts`, `segments.test.ts`, `HighlightedText.tsx`, `CopyEditor.tsx`,
  `useLiveChecks.ts`, `useLiveChecks.test.tsx`, `DiffText.tsx`, `wordDiff.ts`, `wordDiff.test.ts`,
  `copy.test.tsx`
- Modify: `frontend/package.json` (+ `diff@^9`)

**Interfaces (Produces):**
- `interface SpanMark { id: string; start: number; end: number; severity: Severity; source: FindingSource; quote?: string | null; label: string }`
- `interface Segment { start: number; end: number; text: string; marks: SpanMark[] }` (marks ordered blocking
  first, then by start)
- **Offsets:** backend spans (findings, preview findings, terms refs, comments) are Python code-point
  indices; JS strings are UTF-16. `toUtf16Span(text: string, span: { start: number; end: number }): {
  start: number; end: number }` (and a batched `utf16Mapper(text) => (cp: number) => number`) converts at
  the boundary; every `SpanMark` is built through it, so `SpanMark.start/end` are always UTF-16.
- `segmentText(text: string, marks: readonly SpanMark[]): Segment[]` — boundaries at every start/end,
  clamped to `[0, text.length]`, empty and inverted spans dropped.
- `visibleMarks(text: string, marks: readonly SpanMark[]): SpanMark[]` — keeps a mark only when it has no
  `quote` or `text.slice(start, end) === quote`.
- `<HighlightedText text marks activeId? onMarkPress?(id) />` — `<mark data-severity data-source
  data-active aria-describedby={`finding-${id}`}>`; the top mark of a segment decides style.
- `<CopyEditor value onChange marks label aria-describedby? />` — textarea over a highlight backdrop in one
  grid cell (both use `.app-copy-surface` metrics), grows with content, no inner scroll.
- `useLiveChecks(input: CheckPreviewIn | null): { findings: FindingDraftOut[]; marks: SpanMark[]; status:
  'idle' | 'checking' | 'ready' | 'error'; checkedText: string | null }` — `useQuery` keyed
  `['previewChecks', debounced]`, 150 ms debounce, `placeholderData: keepPreviousData`, `previewChecks(body,
  { signal })`. Mark ids `preview-<index>`.
- `wordDiff(before: string, after: string): DiffSegmentOut[]` (jsdiff `diffWordsWithSpace` → `{op, text}`)
- `<DiffText segments: DiffSegmentOut[] />` — `<ins>` / `<del>` with `.app-diff-*`; sr-only "added"/"removed".

- [ ] Step 1: failing tests: `toUtf16Span('Get 💸 cash as low as 5.99%', cp span of "as low as")` slices to
  exactly "as low as" (emoji before the span shifts it by one); astral char inside a span; offsets past the
  end clamp. `segmentText` — no marks → one segment; two disjoint; nested (AI 10–20 inside
  code 5–30 → 5 segments, middle has both, blocking first); identical spans; span past end clamped; empty
  span dropped. `visibleMarks` drops a mark whose quote moved. `wordDiff('as low as 5.99% APR','as low as
  6.49% APR')` → equal/delete `5.99%`/insert `6.49%`/equal. `useLiveChecks` with MSW: typing three times
  within 150 ms sends one request; null input sends none.
- [ ] Step 2: run `npx vitest run --project unit src/ui/copy` → FAIL (modules missing).
- [ ] Step 3: implement; `npm i diff@^9`.
- [ ] Step 4: run → PASS. `copy.test.tsx`: `HighlightedText` renders text exactly once and calls
  `onMarkPress('f1')` on click; `CopyEditor` renders marks for `value`.
- [ ] Step 5: commit.

### Task 2: Findings + form + keyboard + labels shared helpers

**Files:**
- Create: `frontend/src/ui/findings/groupFindings.ts` (+ test), `FindingSummary.tsx`, `frontend/src/ui/labels.ts`,
  `frontend/src/ui/forms/apiErrors.ts` (+ test), `frontend/src/ui/forms/fields.tsx`,
  `frontend/src/ui/useHotkeys.ts` (+ test), `frontend/src/ui/Dialog.tsx`

**Interfaces (Produces):**
- `type FindingGroupId = 'blocking' | 'warning' | 'checklist'`;
  `groupFindings<T extends { source; severity; state; span }>(findings: readonly T[]): { id; label:
  'Blocking' | 'Warning' | 'Checklist'; findings: T[] }[]` — human source → checklist regardless of
  severity; open before resolved, then span start; empty groups omitted. `flattenGroups(groups): T[]`.
- `<FindingSummary severity source message citation quote? suggestedFix? />` — badge row + "message ·
  citation", quote in mono, "Suggested: …".
- `labels.ts`: `PRODUCT_LABELS`, `CHANNEL_LABELS`, `MARKET_LABELS`, `ATTACHMENT_KIND_LABELS`,
  `REOPEN_REASON_LABELS` (`terms_changed: 'Offer terms changed'`, `approval_expired: 'Approval expired'`,
  `drift_detected: 'Live copy changed'`), `ORIGIN_LABELS` (`submission`, `reviewer_edit: 'Reviewer edit'`,
  `fast_track: 'Fast-track'`), `OUTCOME_LABELS` (`approved: 'Approved'`, `approved_with_edits: 'Approved
  with edits'`, `changes_requested: 'Changes requested'`, `rejected: 'Rejected'`), `PARTNER_CHANNELS =
  ['affiliate_page']`.
- `apiErrorBody(error: unknown): ErrorOut | undefined`; `fieldErrorsFrom(error: unknown, fields: readonly
  string[]): { fields: Record<string, string>; form: string | null }` — maps each `ErrorOut.fields[].loc`
  to the last segment that names a known field; anything unmapped joins `form`.
- `fields.tsx`: RAC-based `TextInput`, `TextArea`, `SelectField<T>`, `CheckboxGroupField`, `DateInput`
  (native `type=date` in RAC `TextField`), each with `label`, `errorMessage?`, `description?`.
- `useHotkeys(map: Record<string, (e: KeyboardEvent) => void>, enabled = true)` — ignores events whose
  target is input/textarea/select/contenteditable, or with ctrl/meta/alt, or when a `[role=dialog]` is open
  unless the key is `Escape`.
- `<ModalDialog title isOpen onOpenChange children />` (RAC `ModalOverlay` + `Modal` + `Dialog`).

- [ ] Step 1: failing tests: grouping order and human→checklist; `fieldErrorsFrom` maps `loc ['body',
  'payload', 'title']` → `title`, `['partner_id']` → `partner_id`, unknown → form; non-422 → form message;
  `useHotkeys` fires `n` on body, not inside a textarea, not with meta.
- [ ] Step 2: run → FAIL. Step 3: implement. Step 4: run → PASS. Step 5: commit.

### Task 3: Fixtures, MSW helpers, theme section, routes, nav

**Files:**
- Create: `frontend/src/test/fixtures/review.ts`; routes `frontend/src/routes/items.$itemId.tsx`,
  `submit.tsx`, `mine.index.tsx`, `mine.$itemId.resubmit.tsx` (thin; placeholder feature components replaced
  in later tasks); `frontend/src/routeTree.gen.ts` (regenerated)
- Modify: `frontend/src/theme/theme.css` (one section "Review, intake, My submissions"), 
  `frontend/src/ui/layout/nav.ts` (`to: '/mine'`, `to: '/submit'`)

**Interfaces (Produces):**
- `fixtures/review.ts`: `COPY_V2` (real PL ad text), `itemFixture(overrides?: Partial<ItemDetailOut>):
  ItemDetailOut`, `findingFixture(overrides): FindingOut` whose spans index into `COPY_V2` (built with
  `spanOf(text, quote)`), `FINDINGS_OPEN` (1 blocking code, 1 warning AI, 1 checklist), `reviewHandlers(opts)`
  returning MSW handlers for getItem, listFindings, listComments, listItemAttachments, getItemHistory,
  listDecisions, listPlacements, listVersions, getVersion, getVersionDiff.
- Search schema for `/items/$itemId`: `{ v?: number; compare?: number; tab?: 'findings' | 'comments' |
  'details' | 'evidence' | 'history' }`.

- [ ] Step 1: add routes and run `npm run build` to regenerate the route tree; nav test updated for the two
  `to`s. Step 2: `npm run typecheck && npm run test:run` → PASS. Step 3: commit.

### Task 4: New submission (`/submit`) — subagent

**Files:** Create `frontend/src/features/submit/SubmitPage.tsx`, `submitForm.ts` (+ test),
`EvidencePicker.tsx`, `SubmitPage.test.tsx`.

**Interfaces:** Consumes Tasks 1–2. Produces `submitFormSchema` (generated `SubmitItemBody` extended: partner
required when channel in `PARTNER_CHANNELS`; `planned_last_run >= planned_first_run`; markets ≥ 1).

- Fields: title, product, channel, partner (shown and required for affiliate channels; options from
  `useListPartners`), markets (National, California), planned first/last run, prescreened firm offer
  checkbox, copy (`CopyEditor` + `useLiveChecks` with queued evidence kinds), "Fetch from URL"
  (`fetchCopyFromUrl`; 501 → inline "Fetching from a URL isn't available yet. Paste the copy."), optional
  mockup image (kind `creative`), evidence files each with a kind.
- Live findings list beside the editor via `FindingSummary`, grouped; empty copy → "Checks run as you type."
- Submit: if live findings > 0, an inline confirm strip first: "3 open findings (1 blocking). Reviewers will
  see them." [Submit anyway] [Keep editing]. Then `submitItem` → upload each file → navigate to
  `/items/$id`, toast "CP-123 submitted". 422 → `fieldErrorsFrom` onto fields.
- [ ] Tests: required-field errors on submit; partner required for `affiliate_page`; live findings render
  marks; open-count confirm appears before POST; 422 `loc ['title']` shows under Title; upload called per
  file after create. TDD, then commit.

### Task 5: My submissions (`/mine`) — subagent

**Files:** Create `frontend/src/features/mine/MinePage.tsx`, `waitingOn.ts` (+ test), `MinePage.test.tsx`.

**Interfaces:** `waitingOn(row: ItemRowOut, detail?: ItemDetailOut): { bucket: 'you' | 'compliance' |
'approved' | 'closed'; why: string; action?: 'resubmit' | 'new_round' }`.
- you: `changes_requested` ("Changes requested by {approver}: {reason first line}", resubmit), `withdrawn`
  ("Pulled. Start a new round when the copy is fixed.", new_round), `expired` ("Approval expired. Start a new
  round to run it again.", new_round), `draft`. compliance: `submitted` ("Waiting for a reviewer" or "With
  {assignee}"), `in_review` ("{assignee} is reviewing"), `needs_rereview` ("Back in review: {reopen reason}").
  approved: "Approved · expires {date}". closed: `rejected`.
- `useListItems({ submitted_by_me: true, sort: 'updated', limit: 200 })`; details (`useQueries` getItem) only
  for bucket `you` rows, for the decision reason. Sections with counts; empty → "Nothing submitted yet" +
  New submission button; loading skeleton; error with Retry.
- [ ] Tests for each status's bucket/why; page renders sections and the Resubmit link. Commit.

### Task 6: Resubmit (`/mine/$itemId/resubmit`) — subagent

**Files:** Create `frontend/src/features/mine/ResubmitPage.tsx` (+ test).
- Left: requested changes (latest decision reason + accepted findings of the current version). Center:
  `CopyEditor` prefilled with current version text + live checks. Toggle "Changes vs v{n}" → `DiffText` of
  `wordDiff(current, draft)`. Note field ("What changed"). Submit: `changes_requested` → `resubmitItem`;
  `withdrawn|expired` → `startNewRound({ content_text })`; unchanged text disables submit ("No changes yet").
  Then navigate `/items/$id`.
- [ ] Tests: prefill, diff shows the edited word, correct endpoint per status. Commit.

### Task 7: Review data + gate

**Files:** Create `frontend/src/features/review/gate.ts` (+ test), `useReviewData.ts`, `ReviewPage.tsx`
(layout + loading/error states), `ReviewPage.test.tsx`.

**Interfaces:** `decisionGate({ status, llm_check_status }, findings: FindingOut[], viewingCurrent: boolean):
{ canDecide: boolean; approve: { enabled: boolean; blockers: string[] }; overrideRequired: boolean }`.
Blockers copy: "2 findings to triage" / "1 finding to triage", "AI check running" (running), "AI check
queued" (pending), "Viewing v1 · decisions apply to v3". `canDecide` = status `submitted | in_review`.
- `useReviewData(itemId, versionN?)`: item (polls every 3 s while LLM `pending|running`; invalidates
  findings on transition to `succeeded|failed`), findings for the shown version, attachments.
- Layout: `.app-review` grid (bar row, body = center + 26rem panel, each scrolls). Loading = skeleton of the
  same grid; 404 → EmptyState "CP-{id} not found"; other error → one line + Retry.
- [ ] Tests: gate table (open findings, pending, running, failed → override, skipped, old version); page
  shows skeleton then title; 404 copy. Commit.

### Task 8: Copy pane + version compare + mockup

**Files:** Create `features/review/CopyPane.tsx`, `VersionBar.tsx` (+ tests in `ReviewPage.test.tsx`).
- Version select "v3 · Reviewer edit · Dana · 2d" (search `v`), "Compare with" select (none + other versions,
  search `compare`) → `useGetVersionDiff` → `DiffText`. Highlighted copy with findings as `SpanMark`s
  (`id = String(finding.id)`); clicking a mark activates the finding (and switches to the Findings tab).
  Mockup: first item attachment with kind `creative` and `content_type` image → `<img>` with outline.
  Old version shown → notice "Viewing v1. Decisions apply to v3." with "Show v3".
- [ ] Tests: marks rendered for spans; compare shows ins/del; old-version notice. Commit.

### Task 9: Findings panel, triage, keyboard

**Files:** Create `features/review/FindingsPanel.tsx`, `FindingCard.tsx`, `useTriage.ts`, `ShortcutsDialog.tsx`.
- Groups (Task 2), counts in the tab ("Findings 3", open count). Card: `FindingSummary`, state line
  ("Accepted by X", "Dismissed by X: reason", "Dismissal carried from an earlier version: reason"), actions
  Accept / Dismiss… (inline reason textarea, required, Enter submits) / Reopen. AI cards carry "AI
  suggestion" (SourceTag). LLM status row at top of panel: running ("AI check running…"), pending, failed
  ("AI check failed. Approve needs an override reason." + Retry → `retryLlmCheck`), skipped ("AI review
  carried from v{n}" when latest version is fast-track).
- Mutations update the findings cache from the response and invalidate item + history; errors toast.
- Keys: `n`/`p` next/previous (scrolls card and mark into view), `a` accept, `d` dismiss (focuses reason),
  `e` Approve with edits, `?` shortcuts dialog. Disabled when viewing an old version or not a decider.
- [ ] Tests: n/n/p moves `aria-current`; a posts accept for active; d opens reason and typing "d" in it
  doesn't re-trigger; dismiss without reason blocked; carried label; Retry posts. Commit.

### Task 10: Decision bar, decision panel, edits, re-review, withdrawn

**Files:** Create `features/review/DecisionBar.tsx`, `DecisionPanel.tsx`, `RereviewActions.tsx`, `StatusNote.tsx`.
- Bar (sticky): ItemKey, title, StatusBadge, RiskTierBadge, "Round 2 · v3"; right: Approve (primary),
  Approve with edits, Request changes, Reject (danger). Next to Approve when disabled: the gate's blockers
  as text. Each opens the inline panel: reason (required), evidence checkboxes (item attachments, all
  checked), override reason when `overrideRequired` and outcome is approve*, Request changes prefilled from
  accepted findings (`- message ("quote")`). Approve with edits swaps center to `CopyEditor` (current text,
  live checks with the item's context) + "Changes vs v{n}" diff; submit disabled until text differs.
  Reject → `ModalDialog` confirm "Reject CP-123?". Submit → `recordDecision({ outcome, version_n, reason,
  evidence_attachment_ids, llm_override_reason?, edited_content_text? })`; 409 codes
  `open_findings_block_decision` / `ai_check_pending` / `invalid_transition` show their message inline.
- Decided states: bar shows latest decision "Approved v3 by X · 2d · expires {date}".
- needs_rereview: alert-toned note with reopen reason + live placements count; actions Fast-track approve
  (only when current version `origin === 'fast_track'` and newer than the approved one; reason;
  `bulkFastTrackApprove({ item_ids: [id], reason })`; a skip shows its reason), Reaffirm (`reaffirmApproval`),
  Pull (`pullItem`, ModalDialog confirm, danger). Compare defaults to approved → current.
- withdrawn: neutral note "Withdrawn. Takedown {requested|confirmed} for N placements. The marketer can
  start a new round."
- [ ] Tests: approve disabled with "2 findings to triage"; after triage enabled and posts DecisionIn; failed
  AI requires override; request-changes prefill; reject confirm; edits posts `edited_content_text`;
  rereview fast-track only when available; withdrawn note. Commit.

### Task 11: Comments, Details, Evidence, History tabs

**Files:** Create `features/review/CommentsTab.tsx`, `DetailsTab.tsx`, `EvidenceTab.tsx`, `HistoryTab.tsx`,
`historyText.ts` (+ test).
- `describeEvent(entry, versionNByVersionId: Map<number, number>): string` — one sentence per type, e.g.
  `item.submitted` "Submitted v1", `finding.dismissed` "Dismissed {rule_id}: {reason}" (+ " (carried)"),
  `decision.recorded` "{Outcome label} v{n}: {reason}", `item.reopened` "Sent to re-review: {reason label}",
  `llm_check.failed` "AI check failed", unknown types fall back to the type string.
- Comments: list (author, age, body) for shown version + add form. Details: field list incl. offer terms
  quoted (group `terms_refs` by `offer_terms`: "Personal loan v12 · APR min 7.49%"), legacy fields when
  `is_legacy`. Evidence: attachments (kind, name, size, sha256 first 12, uploader, download link) + upload
  (kind select + file). History: newest first, actor + RelativeAge.
- [ ] Tests: describeEvent cases; comment posts; terms grouping. Commit.

### Task 12: e2e + browser test

**Files:** Create `frontend/e2e/review.spec.ts`, `frontend/e2e/submit.spec.ts`, `frontend/e2e/fixtures.ts`.
- review: stubbed item with 2 open findings → `n`, `a`, `n`, `d` + reason + Enter → Approve enabled → reason
  → POST body has `outcome: 'approved'`. submit: type copy → preview marks visible → submit shows count.
- [ ] Run `npm run test:e2e` → PASS. Commit.

### Task 13: Screenshots + UI review

- Playwright script (`e2e/screens.spec.ts`, runs only with `SCREENS=1`) captures review (open findings, all
  triaged, AI pending, AI failed, approved, needs re-review, withdrawn), intake (empty, live findings), My
  submissions at 1440×900 and 1280×800 into `docs/plan/reviews/ui/review/`. Fresh UI-reviewer subagent with
  screenshots + spec §5 + make-interfaces-feel-better; fix valid findings; record in
  `docs/plan/reviews/ui-review.md`.

### Task 14: Report + PR

- All gates: `lint`, `format:check`, `typecheck`, `test:run`, `build`, `test:browser`, `test:e2e`. Report
  `docs/plan/reports/review-intake.md`; PR "Review screen, intake, and My submissions", body "Closes #10" +
  screenshots.
