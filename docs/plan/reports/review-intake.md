# Report: Review screen, intake, and My submissions (workstream I, issue #10)

Branch `wsI/review-intake`. Plan: `docs/plan/review-intake.md`. UI review: `docs/plan/reviews/ui-review.md`,
screenshots in `docs/plan/reviews/ui/review/`.

Execution: hybrid. The shared layer (copy highlighting, live checks, diff, form fields, fixtures, routes) and
the Review screen were built natively; New submission, My submissions, and Resubmit went to one subagent in
its own worktree, branched from the shared-layer commit and merged back (`wsI/marketer`). Parallel agents in
one worktree would have seen each other's half-edited `theme.css`.

## What shipped

### Shared layer (`frontend/src/ui/`, additive)

| Module | What it does |
|---|---|
| `copy/segments.ts` | `utf16Mapper` / `toUtf16Span`: backend spans are Python code-point offsets, JS strings are UTF-16, so every span is converted at the boundary. Without it, the emoji in `"Need cash fast? 💸 Personal loans as low as…"` shifts every later highlight one character late (tests: `segments.test.ts`, `marks.test.ts`, and a review-screen test that the rendered mark is exactly `no impact on your credit score`). `segmentText` splits at every mark boundary so overlapping and nested findings render each character once; `visibleMarks` hides a mark whose quote no longer sits at its span, so a stale live-check response never mis-places a highlight. |
| `copy/marks.ts` | `marksFromFindings(text, findings)`: stored or preview findings → UTF-16 marks with an accessible label and resolved state. |
| `copy/HighlightedText.tsx` | Read-only copy with `<mark>`s. Severity: blocking = tinted fill + red underline; warning = amber underline, no fill (severity reads without color). Source by underline shape: code solid, AI dashed, checklist dotted. Triaged findings drop to a thin muted line. Clicking a mark selects its finding; repeated clicks on overlapping marks cycle through them. |
| `copy/CopyEditor.tsx` | Textarea over a highlight backdrop in one grid cell with identical text metrics; the backdrop sets the height, so the editor grows and never scrolls internally (no scroll syncing). `CopyEditor.browser.test.tsx` pins the layout match in Chromium. |
| `copy/useLiveChecks.ts` | `POST /checks/preview` as the copy changes. Debounce 150 ms: spec §4.3's 300 ms is the end-to-end budget (the engine takes ~3 ms). React Query keys on the serialized input, so a superseded request is cancelled through `signal` and identical text is answered from cache. |
| `copy/wordDiff.ts`, `copy/DiffText.tsx` | Client word diff (jsdiff `diffArrays` over a tokenizer that keeps `5.99` and `10,000` whole) in the server's `DiffSegmentOut` shape; short unchanged words between two changes fold into one rewrite. Insert = underline on a neutral tint, delete = struck and muted: no status color borrowed. |
| `findings/` | `groupFindings` (blocking → warning → checklist; human items always checklist; ordered by position, never by triage state, so cards don't move under the reviewer), `FindingSummary`, `LiveFindings` (the live-check panel, from the subagent). |
| `forms/` | RAC fields (`TextInput`, `TextAreaField`, `SelectField`, `CheckboxGroupField`, `CheckboxField`); `apiErrorBody`, `apiErrorMessage`, `fieldErrorsFrom` (422 `loc` → form field), `fieldErrorText`. |
| `useHotkeys.ts` | Single-key shortcuts; ignored in text fields, with modifiers, and under a modal. RAC toasts are `role="alertdialog" aria-modal="false"`: the first guard treated them as modal and the shortcuts went dead for 5 s after every decision toast (caught by a test, fixed, pinned). |
| `Dialog.tsx`, `ButtonLink.tsx`, `labels.ts` | `ModalDialog` (confirmations and shortcut help only); router link styled as a button; enum labels, `plural`, `formatDate`, `formatBytes`. |
| `icons.ts` | Two keys: `action.pull` (Minus, the bare sibling of `status.withdrawn`'s MinusCircle, as Approve/Approved) and `action.shortcuts` (Keyboard). |

### Review screen (`/items/$itemId`, `features/review/`)

- **Layout** (product-spec sketch): sticky decision bar on top; copy in the center (version select,
  compare select, legend, the copy sheet, the mockup); a 26 rem side panel with tabs Findings | Comments |
  Details | Evidence | History. Center and panel scroll independently. Search params `v`, `compare`, `tab`
  make every state linkable.
- **Decision bar**: title, key, status, risk tier (hidden below 1366 px; it's on Details), round and version;
  Approve, Approve with edits, Request changes, Reject. The blockers sit beside Approve as text:
  "2 findings to triage · AI check running", "2 accepted findings need a change", "Viewing v1 · decisions
  apply to v2", and with a failed AI check "approving needs an override reason". Decided items show the
  latest decision instead ("Approved v2 by Dana Reyes 4h · expires Apr 23, 2027"). Claim appears on
  unassigned items (only the assignee or a lead may decide).
- **Decision form**: inline under the bar, never a modal: reason (required), evidence checkboxes (item
  attachments, all checked), override reason when the AI check failed. Request changes is prefilled from the
  accepted findings (decisions.md, Ergonomics). Reject and Pull confirm in an alertdialog (§5.7); nothing else
  does.
- **Gates follow the decision service** (E's `reviews/decisions.py`, read on their branch): plain Approve
  needs zero open and zero accepted findings (accepted = must change; the approved version is what goes
  live); Approve with edits needs zero open. Approve with edits swaps the center for the editor with live code
  checks and a "Changes vs v2" diff, and lists the edit's own code findings. If the reviewer's v+1 comes back
  `409 findings_need_triage`, the screen reloads onto v+1 and says so; Approve with edits on a current
  `reviewer_edit` version re-approves it without sending text.
- **Findings**: grouped and counted; each card shows severity, source ("AI suggestion" with an outline glyph),
  "message · citation", the quote, the suggested fix, and its triage state ("Accepted by …", "Dismissed by …"
  + reason, "Dismissal carried from an earlier version (same rule, same text)"). Accept / Dismiss… (inline
  reason, required) / Reopen. Older versions are read-only. AI status row: queued / running (indeterminate bar,
  "Approve unlocks when it finishes"), failed (+ Retry), skipped on fast-track ("AI review carried from v1"),
  finished. The item polls every 3 s while the check is in flight and refetches findings when it lands.
- **needs_rereview**: alert-toned note with the reopen reason and live placements; Fast-track approve vN
  (only when the current version is a generated `fast_track` version newer than the approval), Reaffirm,
  Pull (confirm). "Compare with approved v1" one click away.
- **withdrawn**: neutral note with takedown state ("Takedown confirmed for 1 placement. The marketer can start
  a new round with fixed copy.").
- **Tabs**: Comments (per version, add), Details (fields + "Offer terms quoted" grouped by terms version),
  Evidence (kind, size, uploader, sha256 prefix, download; upload with kind), History (one sentence per event,
  newest first).
- **States**: skeleton in the final layout, "CP-9 not found" with a way back, error + Retry for the item and
  per tab, empty findings ("No findings on v2 … Review the copy and decide.").

### New submission (`/submit`), My submissions (`/mine`), Resubmit (`/mine/$itemId/resubmit`)

From the subagent (Tasks 4–6), reviewed and merged:
- **New submission**: TanStack Form with a zod schema extending the generated `SubmitItemBody` (partner
  required on partner channels, last run ≥ first run, a kind per evidence file). Copy editor with live code
  findings highlighted inline and listed beside it; states for idle, missing context ("Choose a product,
  channel, and market to run checks."), checking, unavailable, none. Submit with open findings shows an inline
  strip first ("4 open findings (4 blocking). Reviewers will see them." Submit anyway / Keep editing). Then
  create → upload each queued file (mockup = kind `creative`) → navigate to the item; a failed upload toasts
  its filename. 422s land on fields (`errorMap.onServer`), cleared on edit. Fetch from URL is wired; the
  backend returns 501 today and the form says "Fetching from a URL isn't available yet. Paste the copy
  instead."
- **My submissions**: sections Waiting on you / With compliance / Approved / Closed with counts; each row
  says who has the ball ("Changes requested by Dana Reyes: Add the full APR r…", "Dana Reyes is reviewing",
  "Back in review: Offer terms changed") and the next action (Resubmit / Start new round). Skeleton, error +
  Retry, empty with New submission.
- **Resubmit**: requested changes (decision reason + accepted findings) above an editor prefilled with the
  current version, live checks, Edit / "Changes vs v2" toggle with the word diff and a change count, note.
  `changes_requested` → `POST /versions`; `withdrawn` / `expired` → `POST /new-round`.

## Interaction model

| Key | Action |
|---|---|
| `n` / `p` | Next / previous finding (all groups, stable order); scrolls card and span into view, focuses the card |
| `a` | Accept the selected finding, then select the next open one |
| `d` | Dismiss: opens the inline reason, focused; Enter dismisses and selects the next open one, Shift+Enter is a newline, Esc cancels |
| `e` | Approve with edits (editor in the center) |
| `?` | Shortcuts dialog |
| `Esc` | Close the reason or the decision form |

Clicking a highlighted span selects its finding (and switches to the Findings tab); the selected finding's
span gets a focus-navy tint. Shortcuts never fire in a text field, with a modifier, or under a modal.

## Span offsets: code points vs UTF-16 (per the orchestrator's note)

Finding `span` values are Python `str` indices (code points); JS `String.prototype.slice` indexes UTF-16
code units. Every astral character (emoji, some symbols) before a span shifts it by one. All marks go through
`toUtf16Span(text, span)` (`ui/copy/segments.ts`), built on `utf16Mapper(text)`, which walks `Array.from(text)`
once and maps each code-point index to its UTF-16 offset. Pinned by: `segments.test.ts` (`'Get 💸 cash as low as 5.99% APR'`:
the UTF-16 start is the code-point start + 1 and the slice is exactly the quote; `'💸💸 rate'` maps
0,1,2,3 → 0,2,4,5; out-of-range ends clamp), `marks.test.ts`, `ReviewPage.test.tsx` (the rendered mark's
text is exactly `no impact on your credit score`, after the fixture's emoji), and `e2e/submit.spec.ts` (the
live-preview mark after the emoji is exactly `as low as`, in Chromium). Live-preview marks also pass
a quote check (`text.slice(start, end) === quote`), so a mismatch hides the mark rather than misplacing it.
The fixtures' copy contains the emoji on purpose, so every review-screen test runs through the conversion.

## API gaps

Nothing under `frontend/src/api/generated` or the OpenAPI was edited. What the UI works around:

1. **No server-side draft, and `SubmitItemIn` has no attachments.** Files upload after the item is created,
   so the post-submit code checks run without evidence kinds while the live preview (which sends
   `attachment_kinds`) had them: rules keyed on evidence (substantiation, rate sheet, prescreen criteria)
   can show a finding after submit that the preview didn't. Fix options: accept `attachment_ids` from a
   pre-upload endpoint on submit, or re-run code checks when an attachment is added.
2. **No single-item fast-track endpoint.** The re-review "Fast-track approve vN" calls
   `bulkFastTrackApprove({ item_ids: [id], reason })` (F's endpoint) and reads the per-item result.
3. **`ItemRowOut` lacks the latest decision reason and `approval_expires_at`.** My submissions fetches
   `GET /items/{id}` for each `changes_requested` row to quote the reason; Approved rows say just "Approved"
   instead of "Approved · expires Apr 23, 2027". Adding `latest_decision_reason` (first line) and
   `approval_expires_at` to the row removes N+1 detail fetches.
4. **`FindingOut.carried_from_id` is a finding id, not a version.** The card says "Dismissal carried from an
   earlier version" without "from v1"; adding `carried_from_version_n` makes it specific.
5. **History payloads carry `version_id` and user ids.** `describeEvent` maps them through
   `item.versions` and `GET /users`; a user id missing from `/users` reads as "a reviewer".
   Server-rendered actor names in the payload (as `actor` already is) would remove the join.
6. **E's `DecisionIn` validator vs E's own contract (on `wsE/review-workflow`).** The decision service says:
   after Approve with edits returns `409 findings_need_triage`, the reviewer triages v+1 and re-posts
   `approved_with_edits` on v+1 *without* text. But `DecisionIn` rejects `approved_with_edits` without
   `edited_content_text` (422). The UI sends `edited_content_text: null` on that re-approve, which will 422
   until E relaxes the validator (allow null when the current version is the reviewer's own
   `reviewer_edit`). Flagged to E via this report; the UI path is tested against the documented contract.
7. **`POST /items/fetch-url`, `POST /items/{id}/versions`, `POST /items/{id}/new-round` return 501 on
   `main`.** The UI is wired to the generated clients and shows the server's message on one line; behavior
   tested with MSW only. (E's branch implements the latter two.)
8. **`MeOut` has no user id.** The UI can't tell "assigned to me" from "assigned to someone else", so Claim
   and the decision buttons are gated by role only; the server enforces assignee/lead, and its refusal shows as the
   server's message under the decision form (Claim failures toast). Adding `id` to `MeOut` lets the bar say "Assigned to Dana Reyes" and hide
   actions the server will refuse.
9. **Generated hooks type errors as `ErrorOut`, but the mutator throws `ApiError`** (with `.body: ErrorOut`).
   `apiErrorBody(error)` bridges it; `instanceof ApiError` detects 404s. An orval `override.mutator` error
   type, or a `TError = ApiError` default, would make the types honest.
10. **Mockup = attachment of kind `creative`.** There's no dedicated mockup field; the review screen shows
    the newest `creative` image attachment under the copy.

Not mine, noted: the shared `queryClient` has no global `onError` toast, so each mutation handles its own
errors.

## Changes outside my ownership

- `frontend/tsconfig.node.json`: `module`/`moduleResolution` `nodenext` → `esnext`/`bundler`, so
  Playwright specs can import `src/test/fixtures` (which import generated types without `.js` extensions).
  No effect on the app build (`tsconfig.app.json`).
- `frontend/src/ui/layout/nav.ts`: `to` added for My submissions and New submission.
- `frontend/src/theme/theme.css`: one new section ("Review, intake, My submissions (workstream I)"), placed
  before App shell, plus one keyframe at the end. No existing rule changed.

(UI review, verification below.)
