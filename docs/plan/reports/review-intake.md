# Report: Review screen, intake, and My submissions (workstream I, issue #10)

Branch `wsI/review-intake`. Plan: `docs/plan/review-intake.md`. UI review: `docs/plan/reviews/ui-review.md`,
screenshots in `docs/plan/reviews/ui/review/`.

Execution: hybrid. The shared layer (copy highlighting, live checks, diff, form fields, fixtures, routes) and
the Review screen were built natively; New submission, My submissions, and Resubmit went to one subagent in
its own worktree, branched from the shared-layer commit and merged back. Parallel agents in one worktree
would have seen each other's half-edited `theme.css`.

## What shipped

### Shared layer (`frontend/src/ui/`, additive)

| Module | What it does |
|---|---|
| `copy/segments.ts` | `utf16Mapper` / `toUtf16Span`: backend spans are Python code-point offsets, JS strings are UTF-16, so every span is converted at the boundary (an emoji before a finding would otherwise shift every highlight one character late). `segmentText` splits text at every mark boundary so overlapping and nested findings render each character once; `visibleMarks` hides a mark whose quote no longer sits at its span (stale live-check responses never mis-place a highlight). |
| `copy/marks.ts` | `marksFromFindings(text, findings)`: stored or preview findings → UTF-16 marks with an accessible label. |
| `copy/HighlightedText.tsx` | Read-only copy with `<mark>`s. Severity: blocking = tinted fill + red underline, warning = amber underline and no fill (so severity reads without color). Source by underline shape: code solid, AI dashed, checklist dotted. Resolved findings drop to a thin muted line. Repeated clicks on overlapping marks cycle through them. |
| `copy/CopyEditor.tsx` | Textarea over a highlight backdrop in one grid cell with identical text metrics; the backdrop sets the height, so the editor grows and never scrolls internally (no scroll sync). A browser test pins the layout match. |
| `copy/useLiveChecks.ts` | `POST /checks/preview` as the copy changes: 150 ms debounce (the spec's 300 ms is the end-to-end budget), React Query keyed on the input so a superseded request is cancelled via `signal` and identical text is cached. |
| `copy/wordDiff.ts`, `copy/DiffText.tsx` | Client word diff (jsdiff `diffArrays` over a tokenizer that keeps numbers like `5.99` whole) in the server's `DiffSegmentOut` shape; insert = underline on a neutral tint, delete = struck and muted (no status color borrowed). |
| `findings/` | `groupFindings` (blocking → warning → checklist; human items always checklist; stable position order so cards never jump while triaging), `FindingSummary`. |
| `forms/` | RAC fields (`TextInput`, `TextAreaField`, `SelectField`, `CheckboxGroupField`, `CheckboxField`); `apiErrorBody`, `apiErrorMessage`, `fieldErrorsFrom` (422 `loc` → form field). |
| `useHotkeys.ts` | Single-key shortcuts that ignore text fields, modifier keys, and open modal dialogs. |
| `Dialog.tsx`, `labels.ts` | `ModalDialog` (confirmations and shortcut help only); enum labels, `plural`, `formatDate`, `formatBytes`. |
| `icons.ts` | Two keys: `action.pull` (Minus, the bare sibling of `status.withdrawn`'s MinusCircle) and `action.shortcuts` (Keyboard). |

### Review screen (`/items/$itemId`, `features/review/`)

(filled in below)

## API gaps

(filled in below)
