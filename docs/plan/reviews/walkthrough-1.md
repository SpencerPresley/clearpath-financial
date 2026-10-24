# Walkthrough review 1: whole app, every role

Fresh-eyes walkthrough before the hosted demo. Main at `a5b59fc` (rechecked on `7cf32a7`; see below), local stack (own DB `clearpath_walk`,
`seed_demo`, uvicorn + Celery worker/beat + Vite on 5173), no Anthropic key. Driven with Playwright at
1440×900 and 1280×800. Screenshots: `docs/plan/reviews/ui/walkthrough-1/` (named `NN-role-what.png`, referred
to below as `shot NN`).

Covered: every guided path in `docs/demo.md` for reviewer, lead, marketer and admin; then keyboard-only through
the reviewer loop, backend-down states, the assistant without a key, import, metrics, terms publish, single and
bulk fast-track, AI-failure override approval, drift simulate/check/restore/reaffirm, notifications, Outbox,
Reset demo, a make-interfaces-feel-better polish pass, and API permission probes (`fetch` from each role's session
against every lead/admin/reviewer-only mutation).

**Counts:** 4 blockers, 18 open should-fix (plus 2 already fixed on main), 17 nits.

**Main moved during the review.** I walked `a5b59fc`. Then #43 (production readiness) and #44 (comment links +
quick-jump) merged, and this branch is rebased on `7cf32a7`. I re-seeded on `7cf32a7` and rechecked:
- **Fixed by #44:** S2 ("Search (soon)" is now a working ⌘K quick-jump, shot 151) and S13 (the duplicate
  re-review notifications are gone, shot 150). They're kept below, marked fixed, so the evidence trail stays intact.
- **Still present:** every blocker. `pricing.py:75`, `LlmStatus.tsx:86`, `decisions.py:358-360` and
  `ResubmitPage.tsx` are unchanged. The files behind S1, S4–S12 and S14–S20 are also untouched by #43/#44
  (`git diff a5b59fc 7cf32a7` on those paths shows only an unrelated `legacy_ref` search filter).

Environment notes, not product findings: the dev CSRF and drift-fetch allowlists are pinned to ports
5173/8000 (`config/settings/dev.py`), so a second local stack on other ports can't sign in and can't run
Check now. Celery's prefork pool crashes on macOS here (`ValueError: not enough values to unpack`); I ran
`--pool=threads`.

---

## Blockers

### B1. Fast-track approves a drift re-review whose partner page still shows the bad copy

- **Role / screen:** Lead (and any reviewer), Queue → Needs re-review → bulk "Fast-track N re-reviews…", and the
  CP-7 review screen.
- **Steps:**
  1. Fresh seed. CP-7 (LendCompare) is `needs_rereview` with reason `drift_detected`. Its latest check is
     `modified`: the live page says 7.99% and "Guaranteed approval for most applicants" (shot 54). The item page
     correctly offers only Check now and Pull.
  2. As lead, publish any personal-loan terms change (I moved APR min from 9.99% to 10.49%; shots 83–85). The
     fan-out generates a fast-track v4 on CP-7, and `reopen_reason` stays `drift_detected`.
  3. Queue → Needs re-review → select all → "Fast-track 7 re-reviews…" → enter a reason → Fast-track approve.
- **Saw:** "Fast-tracked 6 of 7 items · 1 skipped" (shot 88). CP-7 is now `approved` (decision 51, lane
  `fast_track`). Placement 7 is still live and monitored, and its latest check is still `modified`. Partner
  LendCompare now shows CP-7 "Approved, 0 open findings" (shot 95), and Metrics counts CP-7 as a fixed live
  re-review.
- **Single item, same result (re-run on a fresh seed):** after the publish, CP-7's own page puts "Fast-track
  approve v4" first in the decision bar, and the banner changes from "The partner page doesn't show approved v3…"
  to "v4 was generated with the new numbers". The Findings tab says "AI review carried from v3 · only offer-terms
  numbers changed" (shot 131 vs shot 130). The drift explanation disappears from the screen at the moment it matters
  most.
- **Related dead button in the same state:** after Restore original page → Check now (result `unchanged`), the bar
  offers "Reaffirm v3" (shot 132). Submitting it fails with "The current version isn't the approved one. Fast-track it
  or review it." (shot 134). The server is right; the UI is offering an action it can never complete.
- **Expected:** a drift re-review closes only when a check finds the approved copy back on the page (Reaffirm),
  through a full review, or through Pull. Ledger ruling: "Reaffirm on drift_detected only when the latest check is
  unchanged." Fast-track is meant for re-reviews where only numbers changed, and it was never meant to clear a
  page that differs from the approved copy. The product approved live content that makes a guaranteed-approval
  claim and quotes a rate ClearPath doesn't offer. That's the exact failure the tool exists to prevent, and the
  evaluators will be probing for this kind of bypass.
- **Cause:** `backend/reviews/decisions.py:358` checks only `version.origin == FAST_TRACK`. The
  `drift_not_restored` guard (docstring at line 409) protects only reaffirm. In the frontend,
  `features/review/decisionModes.ts:13` (`fastTrackAvailable`) also ignores `reopen_reason`, and `StatusNote.tsx`
  picks the fast-track message before the drift message.
- **Fix:** in `record_decision`'s fast-track lane, refuse when `reopen_reason == drift_detected` and the latest
  check on any live monitored placement isn't `unchanged` (use the same check as reaffirm). Bulk then skips the item
  with that reason. Mirror the rule in `fastTrackAvailable`, keep the drift message first in `StatusNote` while the
  drift is unresolved, and hide Reaffirm when the current version isn't the approved one. Alternatively, make the
  terms fan-out leave drift items alone. Also have the bulk dialog list which items are eligible before you
  confirm: it said "7 items" while it could only ever approve 6.

### B2. The "as low as" suggestion proposes a rate ClearPath doesn't offer

- **Role / screen:** Marketer, New submission (live code checks), and every review screen that shows the finding.
- **Steps:** New submission → Personal loan → copy containing "rates as low as 5.99% APR".
- **Saw:** "Show the full rate range next to this lowest rate … Suggested: 'APRs from 7.49% to 35.99%'". The
  finding directly below it says "This APR isn't offered; current APRs are 9.99%–35.99%" (shots 20, 23).
- **Expected:** suggestions come from the current offer terms (spec §4.2 #1, §4.3 "rate comparisons against
  current offer terms"). A marketer who pastes the suggested text puts a non-offered APR into the ad, and the
  tool contradicts itself in the same panel.
- **Cause:** a hardcoded literal at `backend/checks/engine/rules/pricing.py:75`. The "e.g. 36 monthly payments of
  $337" example in the repayment-terms rule is also fixed text, unrelated to the copy's own $199 or terms.
- **Fix:** build the suggestion from `ctx` terms (`apr_min`/`apr_max` of the current version). The
  `pricing.terms_current` rule already reads them. Add a fixture test that changes the terms and checks the
  suggestion follows.

### B3. An expired item says its approval expired on a future date

- **Role / screen:** Marketer, My submissions → CP-10 → Start new round.
- **Saw:** "Approval expired Mar 19, 2027. Start round 3 to have it reviewed again." on 2026-10-24 (shot 25).
  CP-10 actually expired on 2026-10-18 because the terms changed (`reopen_reason: terms_changed`, event 532). The
  My submissions row also says "Approval expired. Start a new round to run it again." (shot 11), and the demo
  script itself says this one expired "after the rate change".
- **Expected:** the stated reason and date match the record. The marketer is choosing whether to rework copy or
  accept the regenerated numbers, so "why" is the whole message (spec §1 Marketer: "see what's blocking it").
- **Cause:** `frontend/src/features/mine/ResubmitPage.tsx:128` (`RoundContext`) prints `approval_expires_at` for
  every expired item. `features/mine/waitingOn.ts:60` has one fixed string for `expired`.
- **Fix:** branch on `reopen_reason`. For `terms_changed`: "Expired Oct 18 when offer terms v2 replaced v1. v3 has
  the new numbers; check them and start round 3." For `approval_expired`: keep the date. Use the same wording in
  `waitingOn.ts`.

### B4. After a fast-track approval, the AI status names the wrong version

- **Role / screen:** Reviewer/lead, CP-2 review screen → Findings tab.
- **Steps:** Fresh seed. Open CP-2 (needs re-review): the Findings tab says "AI review carried from v3 · only
  offer-terms numbers changed" (shot 30). Fast-track approve v4. Look at the Findings tab again.
- **Saw:** "AI review carried from v4 · only offer-terms numbers changed" (shot 138). v4 is the version that
  was never AI-reviewed. The record says otherwise: `latest_decision.ai_review_carried_from_n` is 3.
- **Expected:** spec §4.2 #4, "The decision records 'AI review carried from vN'". Which version the AI actually
  read is the provenance fact an AI-security evaluator will check first, and the screen states it wrongly right
  after the approval.
- **Cause:** `frontend/src/features/review/LlmStatus.tsx:86` uses `item.latest_decision?.version_n` (the version
  just approved) instead of `latest_decision.ai_review_carried_from_n`.
- **Fix:** read `ai_review_carried_from_n`, and when it's null fall back to "AI check skipped for this version".
  Add a test that fast-tracks v4 and asserts "carried from v3".

---

## Should-fix

### S1. Switching roles in one tab lands you on the previous user's screen
- **Role / screen:** All roles, sign-in.
- **Steps:** As reviewer, open the queue. Account menu → Sign out → pick marketer → Sign in.
- **Saw:** Priya lands on `/queue?view=mine…`, a screen her nav doesn't have, with "Nothing assigned to you · 2
  unassigned items · Show unassigned" (shot 10). Admin signing in after the lead lands on `/library` (shot 110).
  Going to `/` instead gives the right landing (shot 11).
- **Expected:** ledger ruling "landing route by role", and demo.md's "You land on My submissions / Import".
  Evaluators will switch roles in one tab, so every guided path after the first starts on the wrong screen.
- **Cause:** sign-out leaves the URL alone. `SessionGate.tsx:44` only refetches `me`, and the role redirect lives
  only in `routes/index.tsx`.
- **Fix:** navigate to `/` on sign-out (or in `onSignedIn` when the user id changed).

### S2. "Search (soon)" sits in the header of every screen (fixed on main by #44)
- **Role / screen:** All roles, top bar. **Steps:** sign in.
- **Saw:** a disabled search box with the label "Search (soon)" (shot 02 and every later shot). Spec §2 anti-goal: "Fake
  depth: … 'coming soon' screens … fails the project." The ledger says a real quick-jump is in flight. Make sure
  it merges before the demo; otherwise remove the box.

### S3. The decision record isn't visible as a unit anywhere in the app
- **Role / screen:** Reviewer/lead, review screen (all tabs) and queue preview drawer.
- **Steps:** Approve CP-40 with an AI override reason ("Provider outage; read by hand"; the form is shot 135),
  then look at every tab. Separately, fast-track CP-2 and open Details.
- **Saw:** the header shows "Approved v1 by Rachel Okafor now · expires Apr 24, 2027" (shot 137), but the override
  reason appears in none of Findings, History or Details, though the API has it
  (`latest_decision.llm_override_reason`). On CP-2, Details shows the offer terms the *current version* quotes (shot
  35), not the terms versions the decision recorded. There's no rule-set date or evidence hash anywhere. The
  Findings tab's AI line is the only decision-record fact on screen, and it's wrong after approval (B4). No
  frontend file reads `terms_versions`, `ruleset_date`, `ai_review_carried_from_n` or `llm_override_reason`
  (grep). They're only in the evidence-pack zip from the Library.
- **Expected:** product-spec "What it does that a spreadsheet can't" #3, the approval record, is the main argument
  against Excel, and evaluators can't see it without downloading a zip.
- **Fix:** add a "Decision" block to Details (or a History entry that expands) that renders `listDecisions` for the
  current approval: outcome, approver, version, terms vN per product, rule-set date, AI status (ran, carried from
  vN, or overridden with the reason), evidence files with short hashes.

### S4. Age and "Waiting >3 days" count re-reviews from the original submission
- **Role / screen:** Reviewer/lead, Queue and stats strip.
- **Saw:** right after the terms publish, CP-2 had been in re-review for one minute but showed Age "8w" and was
  counted in Waiting >3 days. The stat jumped from 10 to 14 (shot 86). CP-7 shows "5w" though its drift was found
  2 days ago (shot 58). My submissions shows the same CP-2 as "5d" under a column labeled "Updated" (shot 11).
- **Expected:** "Waiting >3 days" is a lead's bottleneck signal (spec §1 Lead). Inflating it on every terms change
  makes it noise. The same item shouldn't show two different ages under two labels.
- **Fix:** measure age from when the item entered its current waiting state (submitted, resubmitted or reopened)
  in both the column and the `waiting_more_than_days` filter, and use one label ("Waiting") on both screens. A
  tooltip can carry "first submitted Aug 26".

### S5. One concept has five names: drift
- **Role / screen:** Reviewer/lead, queue preview drawer, item banner, Details → Where it runs. **Steps:** open
  CP-7 from the queue with Enter, then with o.
- **Saw:** Queue drawer: "Re-review: Drift detected" (shot 121). Item banner: "Re-review: Live copy changed", including for
  *missing* copy (shots 54, 93). Placement chip: "Changed on the page" / "Copy missing". API/docs: `modified`,
  "drift". Terms reopen reason: "Terms changed" in the queue vs "Offer terms changed" on the item.
- **Cause:** two label maps that disagree, `features/queue/labels.ts:23-26` and `ui/labels.ts:53-56`.
- **Expected:** spec §5.4, one term per concept. **Fix:** delete the queue copy, use `ui/labels.ts`
  everywhere, and pick one family: "Live page changed" for the reason, then "Changed" / "Missing" / "Unchanged" for
  check results. Use "Offer terms changed" everywhere.

### S6. Marketers see copy written for reviewers, in error red
- **Role / screen:** Marketer, item page.
- **Saw:** "AI check queued. Approving waits for it." (shot 16). "AI review isn't configured on this server. Give
  an override reason when you approve." in a red banner (shots 17, 23). On CP-40: "Retry, or give an override reason
  when you approve" with no Retry button (shot 12-marketer-direct-items-40).
- **Expected:** red means blocked or refused (§5.2), and §5.4 says errors tell the reader what *they* can do. A
  marketer can't approve or retry anything.
- **Fix:** give marketers role-specific copy in neutral style: "AI pre-review didn't run; your reviewer will
  check this by hand." Keep the reviewer copy for reviewers.

### S7. 403s and 404s are retried for ~7 seconds, then partly handled
- **Saw:** a marketer opening `/metrics` by URL gets about 5 s of skeletons, then "Couldn't load the headline
  numbers. This needs the reviewer or admin role.", "Couldn't load the trend.", and a "Waiting in the queue now"
  strip that stays a skeleton forever (shot 12-marketer-direct-metrics). After Reset demo, reloading the import
  page for a deleted job shows a blank "Import" for about 7 s before "Import 2 not found" (shot 118).
- **Cause:** `frontend/src/api/queryClient.ts` keeps React Query's default `retry: 3` with backoff for every
  status.
- **Fix:** `retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 3`. Give Metrics
  the same designed role gate Import has ("Import is for admins", shot 12-marketer-direct-import).

### S8. The keyboard loop dead-ends after a decision
- **Role / screen:** Reviewer, review screen.
- **Saw:** j/k/Enter/o in the queue and n/p/a/d/e/⌘Enter on the review screen all work, and accept moves to the
  next open finding (shots 41–50). There's no shortcut for Approve, Request changes or Reject: reaching Request
  changes from the findings took 8 Shift+Tabs (shot 49). After the decision, focus drops to `<body>` and there's
  no next-item or back-to-queue key (shot 51).
- **Expected:** spec §4.3 Review, "navigate the queue, open an item … without the mouse", and lever 2, faster
  rounds.
- **Fix:** shortcuts for the decision buttons (for example ⇧A, ⇧R, ⇧X, with the existing reason form), and after
  a decision, "Next in queue (j)" that opens the next row of the view the reviewer came from.

### S9. Raw identifiers in the audit trail and Details
- **Role / screen:** Reviewer/lead, review screen → History and Details. **Steps:** open CP-2, check both tabs.
  Also approve CP-40 after a PL terms publish.
- **Saw:** History shows `llm_check.started`, "Dismissed human.reg_b_discouragement on v3" and "Accepted
  claims.credit_impact on v2" (shot 34). Details → Offer terms quoted shows "apr min: 9.99%" twice, "term months:
  24" and "term months: 60" as separate rows, and "origination fee min pct" (shot 35), which also triggers a React
  duplicate-key console error (`features/review/tabs.tsx:149`). Offer terms itself uses "APR min" and "Loan terms
  (months)" (shot 81). A 409 on approval reads "This version quotes offer terms no longer in effect
  (personal_loan v2)" (shot 137-lead-cp40-approve-result).
- **Expected:** §5.4 domain-native copy. The History tab is what an examiner reads.
- **Fix:** reuse the Offer terms field labels in `tabs.tsx`, and dedupe by field and value. Map rule ids to rule
  titles and every event type to a sentence (add a test that fails on an unmapped event type).

### S10. Sign-in reports server failures as a wrong password
- `ui/layout/session.ts:46` turns every non-401 `ApiError` (403 CSRF, 429 throttle, 500) into "Couldn't sign in.
  Check the email and password." I hit it locally on a CSRF origin mismatch (the server logged `Origin checking
  failed`; the screenshot was overwritten when the retry succeeded). On the hosted demo, a WAF or CSRF problem
  would send evaluators off retyping a correct password.
- **Fix:** keep that message for 400 bad-credentials only. Use "Sign-in was refused by the server (403). Reload
  the page and try again." for 403, and "The server had a problem. Try again in a minute." for 5xx.

### S11. Suggested fixes can't be applied; people retype them
- **Role / screen:** Marketer (Resubmit, New submission) and reviewer (Approve with edits). **Steps:** open
  CP-22 → Resubmit, or CP-26 → press E.
- **Saw:** Marketer resubmit (shot 13), the new-submission panel (shot 20) and reviewer Approve with edits (shot 53) all
  show "Suggested: …" as plain text. "Fix it once" (§1 Marketer) and approve-with-edits throughput both rely on
  copying it.
- **Fix:** an "Apply" button on findings that have a span and a literal suggestion. It replaces the span in the
  editor, and code checks re-run as usual.

### S12. Suggestion and citation text that undermines trust
- **Role / screen:** Reviewer (CP-26 Findings) and marketer (CP-22 Resubmit). **Steps:** open each and read the
  suggestions.
- CP-26's AI suggestion replaces "Rates this low won't last, so go look before they're gone!" with "Checking your
  rate takes two minutes.", which is the sentence directly before it, so applying it duplicates a line (shot 52;
  scripted seed content).
- Issuer-line suggestion: "The ClearPath Card is issued by Harborview Bank, N.A.." (double period;
  `checks/engine/rules/card.py:282` appends "." to a bank name that ends in one). Shot 13.
- Citation shown to marketers: "ClearPath card program policy (decisions.md, Company facts); legal basis
  unverified" (`card.py:103`). An internal doc filename and "unverified" have no place in a compliance citation.
  Use "ClearPath card program policy" and keep the caveat in code comments.

### S13. Duplicate notifications, against the ledger ruling (fixed on main by #44)
- **Role / screen:** Reviewer, notification bell. **Steps:** fresh seed, sign in as Dana, open the bell.
- **Saw:** Dana's inbox has pairs at the same minute for CP-21, CP-13 and CP-5: "… is back for your review" plus
  "… needs re-review · offer terms changed" (shot 62). Ledger ruling: "one notification per action — a reopen's
  sticky reassignment doesn't also send 'back for your review'." Either the seed predates the dedupe, or the
  dedupe isn't wired. Reseed after fixing, and add a seed-level assertion.

### S14. The drift evidence is squeezed into the side panel
- **Role / screen:** Reviewer/lead, CP-7 → Details → Where it runs. **Steps:** fresh seed, open CP-7 Details at
  1440 and at 1280.
- **Saw:** CP-7's "Approved v3 compared with the page" diff is a single flattened paragraph in the ~390 px Details panel,
  under the metadata. Meanwhile the 760 px center shows the unchanged approved copy (shots 54, 123). Drift is the
  most persuasive demo moment, and its evidence is the hardest thing on the screen to read.
- **Fix:** while an item is `drift_detected`, give the center pane a "Live page vs approved vN" mode (same diff
  component as version compare), with the side panel keeping the check metadata.

### S15. The import demo shows nothing after a seed
- **Role / screen:** Admin, Import → Load sample tracker → Save and continue.
- **Saw:** 0 ready to import. "Warnings · 206 in 180 rows", 178 of which are "MCR-… is already imported; skipped".
  The interesting mess handling (e.g. "Approval date taken from the last round") is buried among them and also
  labeled "Skipped" (shot 113). The Values step was marked done without being shown. "Recent imports" dates the
  go-live import "Oct 23, 2026", though native history starts Aug 17 (shot 111).
- **Expected:** spec §4.3 Import, "map columns, map status values, preview the problems". The admin's whole demo
  path is this screen.
- **Fix:** collapse already-imported rows into one info line ("178 rows already imported from this tracker"), keep
  the per-row mess outcomes visible with their actual outcome (Imported with adjustment and so on), and always show
  the Values step with the mapping it inferred. Date the seeded import at go-live.

### S16. Lead and admin needs from spec §1 have no screen
- Lead "workload balance": no per-reviewer load anywhere. The queue's Assignee filter is the closest (shot 80).
- Admin "Users": no screen. `POST /api/admin/users` and `PATCH /api/admin/users/{id}` return 501 "User management
  isn't available yet." Admin also has no Metrics link, though the API allows admin (shot 110).
- There's also no availability toggle in the account menu (shot 03), though `PATCH /api/me {is_available}` exists
  and the demo story depends on Leah being out of office. Either build minimal versions (a load column grouped by
  assignee; a read-only users list with an availability toggle) or record them as out of scope in `decisions.md`,
  so the spec and the product agree.

### S17. The item header shows the previous round's decision next to the new status
- **Role / screen:** Marketer and reviewer, item header. **Steps:** as Priya, resubmit CP-22 with the issuer line.
- **Saw:** after Priya resubmits CP-22: status "Submitted", header right "Changes requested v2 by Samuel Ortega 9d" (shots
  16, 17). It reads as two current states. **Fix:** once the item has moved past that decision, show it as history
  ("Last round: changes requested on v2") or drop it from the header.

### S18. Reset demo leaves stale screens behind
- **Role / screen:** Admin, account menu → Reset demo…, with Import open. **Steps:** Import → Load sample tracker
  → Save and continue → Reset demo → confirm.
- **Saw:** with the Import page open on job 2, Reset demo finished ("Demo reset · 44 items seeded", shot 117) but the page
  kept showing the deleted job's preview with an "Import 0 items" button (it 404s in the background). Same for any
  open item. **Fix:** on the reset-done notice, `queryClient.clear()` and navigate to the role's landing page.

### S19. Library "Approved to run" lists legacy items whose approval has expired (borderline blocker)
- **Role / screen:** Any role, Library → Approved to run. **Steps:** open the Library.
- **Saw:** CP-198 (expires Aug 23, 2026), CP-203 (Sep 20, 2026) and CP-210 (Sep 25, 2026) are on the first page
  under "Approved to run", with no expired marker (shot 100). Today is Oct 24, 2026.
- **Expected:** this tab answers "can I run this?", and for these rows the answer is no. Legacy items are
  excluded from the expiry sweep by design (spec §4.2 #7), so their status stays `approved` forever. That makes
  the Library the one place where expiry has to be enforced. I kept it out of the blockers because each date shown
  is true and the cause is a filter, but a marketer reusing creative from this list would run expired content.
- **Fix:** exclude rows with `expires < today` from Approved to run, and show past dates as "Expired Aug 23,
  2026" in the neutral expired style wherever they still appear (precedents, partner history).

### S20. In-review items that quote superseded terms aren't flagged until Approve
- **Role / screen:** Lead/reviewer, CP-40 review screen. **Steps:** publish PL terms v3 (APR min 10.49%), open
  CP-40 (in review, quotes 9.99%), triage all three findings, click Approve, fill in both Reason and Override
  reason, submit.
- **Saw:** the Findings tab still says "all triaged" and nothing mentions the rate. Only after both reasons
  are typed does the form show "This version quotes offer terms no longer in effect (personal_loan v2). Request
  changes or edit the rates." (409; shot 137-lead-cp40-approve-result).
- **Expected:** the server is right to refuse (§4.1, approvals reference current terms). But the reviewer should
  know before triaging that the copy quotes retired terms. Lever 2 (faster rounds) means not finding out at the last
  click.
- **Fix:** on a terms publish, re-run `pricing.terms_current` on the current version of in-review items for that
  product (or flag them in `StatusNote`: "Quotes PL v2; v3 is now in effect"), and disable Approve with that reason
  shown in the decision bar's status line.

---

## Nits

1. **Waiting >3 days shows "3d".** Floor rounding makes CP-35, CP-36, CP-37 and CP-38 read as not meeting the
   filter they're listed under (shot 58), and demo.md says CP-35 "has waited more than three days". Show "3.4d"
   under 7 days, or round up in this view.
2. **Date formats mix.** "Oct 18, 2026" (most screens), "2025-09-26" (import outcomes), "text effective
   2026-07-21" (every Reg B citation), and "10/22/2026, 2:40:00 PM" in the queue age tooltip
   (`features/queue/columns.tsx:159` uses `toLocaleString`) vs "Oct 22, 2026, 2:40 PM" in My submissions
   (`ui/RelativeAge.tsx`). Route them all through one formatter in `ui/labels.ts`.
3. **Narrow layouts drop key columns.** At 1440 with the preview drawer or the assistant open, the queue hides
   Risk, Partner, Assignee and Round (shots 42, 61). At 1280 titles truncate to "LendCompare: best debt …"
   (shot 121), and the review header drops the risk chip (shot 122 vs shot 12-marketer-direct-items-40).
4. **Fast-track reason is never prefilled.** The placeholder is "e.g. Only the offer-terms numbers changed", which
   is the reason in nearly every case (shot 32). Prefill it, so the step really is one click.
5. **"The model provider returned 529."** is jargon for a compliance reviewer (shot 46). Use "The AI service was
   overloaded and didn't answer after 4 tries."
6. **Resubmit page shows the same finding twice:** in Requested changes and in Code checks (shot 13).
7. **Precedent snippets start mid-word:** "er 48 months at 10.49% APR…" (shot 101). Snap to a word boundary
   and add a leading "…".
8. **The header health badge stays "connected" after a failed mutation.** It polls every 30 s
   (`features/system/ApiStatusBadge.tsx:7`). Trigger a recheck on network errors, so the "changes won't save"
   banner shows up with the failing toast (shots 70–71).
9. **"Live · Checked daily" next to "Daily check against v1 · 8d"** on CP-23 before the demo (shot 90). Seed
   daily checks, or say "Last checked 8d ago".
10. **Metrics vs queue count re-reviews differently.** Metrics says "3 re-reviews open" while the queue says 2
    Needs re-review, because Metrics includes withdrawn CP-13 (takedown unconfirmed; shot 97). Label it "3 live
    fixes open" or list the withdrawn one separately.
11. **Brand navy is used for a data series.** The Metrics "Native" bars use navy, which §5.2 reserves for brand
    and primary action (shot 96).
12. **Engine version is newer than the decision.** Seeded decisions dated Sep 19 record
    `engine_version: 2026-10-24.3` (CP-10 decision 16). An examiner reading the record would see an engine
    version newer than the decision. Stamp seeded decisions with the seed clock's version.
13. **The assistant only reveals "not configured" after a send.** The error says "(no API key)", and the failed
    thread is saved to Threads (shot 61). Disable the input with "Assistant isn't available on this server" up
    front. Lower priority, because the hosted demo has a key.
14. **"Code checks on the whole page: 1, 1 not on the approved copy"** (shot 93). Reword to "1 code finding on
    the page, not in the approved copy".
15. **Waiting on you is sorted by recency, not action.** CP-22, the one changes-requested item, sorts third behind
    withdrawn and expired items (shot 11). Put Changes requested first.
16. **Bulk bar offers fast-track to items that can't take it.** "Fast-track 1 re-review…" appears for CP-16, an
    approval-expiry re-review that can't be fast-tracked (shot 88). Disable it with a tooltip when no selected item
    qualifies.
17. **Small hit areas on frequent controls** (measured at 1440, queue). Filter clear × is 25×24, the
    keyboard-shortcuts button 28×28, the bell 32×32, the row checkbox's label 36×35. The skill's floor is 40×40.
    Density is a deliberate §5.1 choice, so extend the hit area with a pseudo-element rather than growing the
    visible control.

---

## Polish checklist (make-interfaces-feel-better)

Measured with `getComputedStyle` / `getBoundingClientRect` on the queue at 1440×900.

| Check | Result |
|---|---|
| Tabular numbers on dynamic figures | Pass: stats strip and Age column are `tabular-nums`. |
| Font smoothing | Pass: body is `antialiased`. |
| No `transition: all` | Pass: 0 elements with `transition-property: all` and a non-zero duration. |
| Minimum hit area 40×40 | Fail on four frequent controls (Nit 17). |
| Restraint (§5.6) | Pass: no sparkle/wand icons, gradients, emoji or celebratory copy. Cards are used for panels, not everything. |

---

## Consistency audit

| Thing | Where it holds | Where it breaks |
|---|---|---|
| Status colors/icons | Needs re-review = filled red-orange + rotate icon in queue, board, My submissions, terms impact, drawer. In review = blue outline + eye. Approved = green + check. Expired/Withdrawn = slate with distinct icons (§4.2 #6). | Needs re-review is a filled badge and every other status is outlined. Defensible as "act now", but it's the only filled one. |
| Finding source | Code check / AI suggestion / Checklist labeled with distinct icons everywhere; legend in the copy pane uses solid / dashed / dotted underlines. | none found |
| Glossary | Item, Version, Round, Finding, Placement, Partner consistent. | Drift (S5); "Terms changed" vs "Offer terms changed"; "Age" vs "Updated" (S4). |
| Button verbs | Decisions use the spec's verbs. "Start new round" and "Resubmit" are used consistently. | "Fast-track approve v4" vs "Fast-track 7 re-reviews…" vs dialog "Fast-track approve 7 items". Fine, just wordy. |
| Dates | "Mmm d, yyyy" on most screens. | Nit 2. |
| Empty states | Queue "Nothing assigned to you · 2 unassigned items · Show unassigned" (§5.5's own example); board columns "No items"; Import role gate. | Metrics role gate (S7). |
| AI wording | No "violation"/"non-compliant" in the UI (grep; `checks/llm/screen.py` screens it out of model output). | none found |

## Permission probes (no leaks found)

As reviewer: terms publish and impact preview, demo-page edit, bulk assign, partner edit, import list/sample,
reassigning another reviewer's item and demo reset all returned 403 with the required role named. As marketer:
accept/dismiss finding, decision, claim, risk-tier edit, notes on someone else's item, fast-track, reaffirm, pull,
drift check, reassign, LLM retry, comment or resubmit on another marketer's item, and metrics all returned 403.
Enforcement is in services, as spec §4.3 requires. The admin user endpoints return 501 (S16).

## What works well

- **Live code checks.** Findings land about 280 ms after typing stops, with spans highlighted in the copy (shot
  20). Submitting with open findings shows an inline count and "Submit anyway / Keep editing" instead of a modal
  (shot 21).
- **Request changes is prefilled from the accepted findings** with their quotes (shot 50), which is lever 1
  working.
- **Terms impact preview and confirm** ("4 approved items quote v2; 4 will need re-review…") matched the
  outcome exactly (shots 83–85). The fast-track diff for CP-2 is correct to the dollar ($15,000 / 48 mo / 9.99% →
  $380.37).
- **Drift demo.** Simulate → Check now → "Copy missing" → re-review took under 10 s against a real fetch (shot
  93). Restore original page → Check now → `unchanged` brings back Reaffirm, as demo.md describes (shot 132).
- **The AI-failure override** is a separate, required "Override reason" field below the decision reason, with
  "The AI check failed. This is recorded on the decision." (shot 135). The AI-never-approves rule is visible in the
  UI, not just in code.
- **Outbox empty state:** "Demo mail: nothing leaves ClearPath. No emails yet … Open the assistant" (shot 140).
- **Stats strip ↔ view parity.** Each count matched its view's row count (checked twice: 18/5/2/11/4 at landing,
  18/3/2/10/3 later).
- **Metrics** separate native and imported figures, drill to items, and carry the strongest single number in the
  product: median time to first review of 22.2 h native vs 14.0 d imported (shot 96).
- **Error and empty states** are mostly designed: a backend-down mutation toast, a cold-load "Couldn't load your
  account" with Retry, the queue empty state, and the Import role gate.
- **Reset demo** runs in about 10 s in the background with a completion notice.
- The visual language is calm and dense, with no sparkles, gradients or celebratory copy (§5.6 is clean).

## First 3 minutes as each role

**Reviewer (Dana).** She lands on a five-row queue whose order explains itself: two red-orange re-reviews,
then high-risk items. A stats strip sits above. Pressing `?` shows j/k/o, and CP-2 opens to a banner saying
exactly why it's back ("Offer terms changed … v4 was generated with the new numbers") plus a one-click diff that
shows only 9.49→9.99 and 376→380. That's the clearest "beats Excel + email" moment in the product: no
spreadsheet ever told anyone which approved ads quote a rate that just changed. After she fast-tracks it, the
screen claims the AI review was carried from v4 (B4), and the approval never shows what it was approved against
(S3). After deciding there's no "next" (S8). The evaluator understands the product in about 90 seconds; on
`a5b59fc` the next thing they saw was "Search (soon)" (S2, fixed by #44).

**Compliance lead (Rachel).** The Offer terms page with its impact preview is excellent and makes the fan-out
concrete. The drift demo works and reads like real monitoring. But a lead who publishes a rate change and then
uses the obvious bulk action, or the primary button on CP-7 itself, approves the LendCompare listing whose live
page says "Guaranteed approval" (B1). An
AI-security evaluator who tries "what happens if I bulk-approve after a terms change" finds a control bypass in
the most security-shaped feature. The Waiting >3 days count also jumps by four the moment she publishes (S4), so
the bottleneck signal stops meaning anything right when she's looking at it.

**Marketer (Priya).** If she signs in after another role in the same tab, she starts on a reviewer queue she
can't use (S1). From `/` she gets My submissions, which is the best "no more 'any update?' emails" screen
in the app. New submission makes the product's case on its own: paste risky copy and nine findings with
citations appear before the cursor stops. But the second suggestion tells her to write "APRs from 7.49%", a rate
the next finding says isn't offered (B2). "Start new round" on CP-10 tells her the approval expired in
March 2027 (B3). She'd come away thinking the tool is fast but not always right, which is the one impression a
compliance tool can't afford.

**Admin (Avery).** Import loads, but re-running the sample shows 0 rows to import and 178 "already imported"
warnings (S15), so the migration story, a spec §2 goal, never gets demonstrated after a seed. There's no Users
screen (S16). Reset demo is clean and fast. An evaluator would learn that an import happened, not how well
it handles the messy tracker. Pointing them to `samples/README.md` or showing the preview from a fresh DB would
fix the impression.
