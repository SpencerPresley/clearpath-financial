# UI review: Review screen, New submission, My submissions (workstream I)

Screenshots: `docs/plan/reviews/ui/review/` (production build, API stubbed by `e2e/stubApi.ts`, Inter loaded),
each at 1440x900 and 1280x800. Regenerate with `SCREENS=1 npx playwright test e2e/screens.spec.ts`.

| Screen | States |
|---|---|
| Review `/items/$id` | `review-open-findings`, `review-all-triaged` (Approve form open), `review-ai-pending`, `review-ai-failed`, `review-approved` (History, mockup), `review-needs-rereview` (terms changed, fast-track available, comparing v1→v2), `review-withdrawn`, `review-compare`, `review-edit` (Approve with edits) |
| New submission `/submit` | `intake-empty`, `intake-live-findings`, `intake-confirm` |
| My submissions `/mine` | `mine` |
| Resubmit `/mine/$id/resubmit` | `resubmit-edit`, `resubmit-diff` |

Reviewer: a fresh subagent with the screenshots, spec §5 (binding), product-spec "Review screen layout", the
make-interfaces-feel-better checklist, and the source; it hadn't seen the build. The marketer screens
also had a self-review pass by their builder at 1440 and 1100 (key column wrap, field shift when Partner
appears: fixed before merge).

## Findings and resolutions

1 blocker, 11 should-fix, 7 nits. Fixed: 17 (3 of them in part: layout in #7, terms versions in #10,
age header in #12). Declined with reasons: 2.

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | blocker | At 1280 the gate note ("AI check running · 1 accepted finding needs a change") painted over the key/status/round row and truncated the title to "Fall persona…". | **Fixed.** The note moved to its own line under the buttons, right-aligned (`.app-decision-bar-note`); the meta row clips. `review-ai-pending-1280x800.png` now shows the full title and meta. |
| 2 | should | The AI status said "Approve unlocks when it finishes" while an accepted finding still blocked Approve; "approve with an override reason" while Approve was off. | **Fixed.** "Approving waits for it." / "Retry, or give an override reason when you approve." Both true whatever else blocks. |
| 3 | should | "1 accepted finding needs a change" said why, not what to do. | **Fixed.** When accepted findings are the only blocker, the note continues "· Approve with edits or Request changes" (`approveNote`, tested). Approve with edits stays enabled while the AI check runs, on purpose: the reviewer can draft the edit; its submit button is gated and the panel says why. |
| 4 | should | Overlapping findings: the AI warning inside the blocking code span drew no line. | **Fixed.** The second finding on a segment renders its own underline 7px below the first (nested inline decorations both paint), in its own severity color and source style. Visible in `review-open-findings` as the dashed amber line under "as low as". Tested. |
| 5 | should | Accepted spans (must change) looked like dismissed ones. | **Fixed.** Accepted spans keep their severity color on the 1.5px line; dismissed go muted. `data-accepted`, tested. |
| 6 | should | The suggested fix was hidden on accepted cards and in the edit's findings, exactly when the reviewer types the fix. | **Fixed.** Shown on accepted (not dismissed) cards and in "code findings in your edit". |
| 7 | should | Approve with edits: the form sits above the editor, so keyboard submit meant Shift+Tab backwards; no Mod+Enter anywhere. | **Fixed (keyboard).** ⌘/Ctrl+Enter submits the open decision when focus is in its form or the editor (nowhere else, not under a modal, not while the submit is disabled); shown next to the submit and in the shortcuts dialog. Tested. Layout kept: moving the form under the editor would split the decision form across two scroll regions for one mode. |
| 8 | should | Triaged cards kept full red "Blocking" pills, so a finished panel still looked alarming. | **Fixed.** Non-open cards render the severity pill outline-only and muted (glyph and word keep the severity). |
| 9 | should | Withdrawn item: bar said "Approved v2 by Dana Reyes" beside the "Withdrawn" chip. | **Fixed.** Withdrawn/expired read "Was approved v2 by Dana Reyes 4h". |
| 10 | should | "Reaffirm" had no version; under terms_changed it re-approves copy quoting superseded terms. | **Fixed.** Button "Reaffirm v1", panel title "Reaffirm the approval of v1", and under `terms_changed` an alert line: "v1 quotes the offer terms that changed. Reaffirm only if those numbers are still offered; otherwise fast-track the updated version or pull it." Naming the terms versions in the banner needs data the item doesn't carry (API gap list). |
| 11 | should | Intake confirm strip: the focused Submit unmounted and focus was lost; no live region. | **Fixed.** "Submit anyway" takes focus; the count line is `role="status"`. |
| 12 | should | My submissions: "Changes requested by Dana Reyes: …" repeated the badge and truncated the useful part. | **Fixed.** "Dana Reyes: Add the full APR range…". The age column keeps its sr-only header: every row's age has an absolute-time tooltip, and a visible header row on 1–3-row sections costs more than it explains (judgment). |
| 13 | nit | Legend: "AI" too short for its dashes to show; no checklist entry. | **Fixed.** "Code check", "AI suggestion", "Checklist" (dotted), matching the source tags. |
| 14 | nit | The selected span split into two rounded pills at a finding boundary. | **Fixed.** Marks have no radius. |
| 15 | nit | Two navy Approve buttons while the Approve form is open. | **Fixed.** The bar's Approve / Fast-track drop to the pressed secondary style while their form is open. |
| 16 | nit | Groups mix axes: a blocking checklist item would sort below warnings. | **Declined.** The brief and product-spec order is blocking → warning → checklist; checklist items are human prompts (rules engine: `kind="human"` only), a different job from triaging machine findings. Revisit if a blocking checklist item ever exists. |
| 17 | nit | "findings not dismissed before come back open on v3". | **Fixed.** "findings you haven't dismissed reopen on v3". |
| 18 | nit | Edit/diff toggle: ghost button on review, segmented control on Resubmit. | **Fixed.** Both use the segmented control (RAC ToggleButtonGroup). |
| 19 | nit | An open decision panel pushes the copy down ~238px. | **Declined for now.** The panel is capped at 45vh and scrolls; the alternative (overlay drawer) hides the copy the reason is about. Worth revisiting with real usage. |

Also from the review:
- **Data gap in the stub, not the UI:** the approved state's History lacked its approval event. The stub
  now takes a `history` option and the approved capture includes "Approved v2: …".
- **Q3 (AI phrased as a decision):** nothing in these screens. A future risk the reviewer raised: severity
  comes from the rule, so an LLM rule marked `blocking` would get the red pill and the Blocking group. When
  LLM rules land, either cap them at warning or keep "AI suggestion" beside the pill as a spec decision.
  Carried to the report.
- **Q4 (slower than Excel + email):** "use last dismissal reason" and "next item after deciding" are real
  costs. The second depends on the queue (H2's screen) and is listed as follow-up; the first is a small
  follow-up in `DismissForm`.

## Kept (reviewer's list)

- Approve visible but disabled with the reason beside it, wired through `aria-describedby`.
- Stable card order by position; A/D hints on the active card; selection advances after triage.
- AI wording: "AI suggestion" tag, "may need…", inline citation, "Suggested:"; "AI review carried from v1 ·
  only offer-terms numbers changed" on fast-track.
- Diffs without status colors, with a change count.
- Request changes prefilled from accepted findings; Resubmit puts the request above the editor.
