# Walkthrough review 2: hosted demo plus local mutations

Second fresh-eyes walkthrough, done after the take-home was submitted, with evaluators already using the hosted demo.

- **Hosted, read-only:** https://clearpath.spencerpresley.com, serving `50c8f09` (Placements #66). The Deploy run on that commit succeeded, and `f7f38f4` after it changes only the ledger. I signed in as reviewer, lead, marketer and admin and only navigated and read. The Playwright context aborted every non-GET request except the login POST, so nothing could change by accident. The only blocked calls were the live-check previews that the Resubmit page fires on load.
- **Local, for anything that changes state:** main at `f7f38f4` on its own DB (`clearpath_walk2`) and Redis DB 9. Uvicorn on 8000, a Celery worker with `--pool=threads -B`, Vite on 5173, `seed_demo`, no Anthropic key.
- **Viewports:** 1440×900 and 1280×800, driven with Playwright scripts.
- **Screenshots:** `docs/plan/reviews/ui/walkthrough-2/`, named `NN-role-env-what.png`. 01–20 are findings and 30+ are things that work.

**Before anything else, I checked that hosted matches local.** The reviewer queue and CP-2, CP-7 and CP-40 render the same text on both. That makes local a faithful stand-in for every mutating flow.

## Counts

**20 issues: 1 blocker, 11 should-fix, 8 nits.** All are labelled `walkthrough-2`. I found no permission leaks.

| # | Severity | Finding | Env |
|---|---|---|---|
| [#67](https://github.com/SpencerPresley/clearpath-financial/issues/67) | Blocker | Legacy items open to a review screen stuck on skeletons; the tracker record isn't shown | hosted |
| [#68](https://github.com/SpencerPresley/clearpath-financial/issues/68) | Should-fix | Expired legacy approvals still show green "Approved" on partner pages, quick-jump and the item header (77 of 139) | hosted |
| [#69](https://github.com/SpencerPresley/clearpath-financial/issues/69) | Should-fix | Workload panel goes stale after bulk fast-track | local |
| [#70](https://github.com/SpencerPresley/clearpath-financial/issues/70) | Should-fix | "Check this page daily" accepted without a web address; never runs | local |
| [#71](https://github.com/SpencerPresley/clearpath-financial/issues/71) | Should-fix | Reset dialog says "People and sign-ins stay"; reset removes added people | hosted + local |
| [#72](https://github.com/SpencerPresley/clearpath-financial/issues/72) | Should-fix | Deactivate is one unconfirmed click; doesn't say where the items went | local |
| [#73](https://github.com/SpencerPresley/clearpath-financial/issues/73) | Should-fix | Withdrawn CP-13 shows a future approval expiry and a "Live" placement | hosted |
| [#74](https://github.com/SpencerPresley/clearpath-financial/issues/74) | Should-fix | AI-failure banner still says "Retry … when you approve" after the decision | local |
| [#75](https://github.com/SpencerPresley/clearpath-financial/issues/75) | Should-fix | Drift re-review: Findings says "all triaged" and the queue shows 0 while the page has 2 blocking findings | hosted |
| [#76](https://github.com/SpencerPresley/clearpath-financial/issues/76) | Should-fix | Board shows Claim on other reviewers' cards (403, or a silent takeover for leads) | local |
| [#77](https://github.com/SpencerPresley/clearpath-financial/issues/77) | Should-fix | Frontend CI red on main (flaky `signInRouting` test) | CI |
| [#78](https://github.com/SpencerPresley/clearpath-financial/issues/78) | Should-fix | Nothing leads a marketer to record placements after approval | local |
| [#79](https://github.com/SpencerPresley/clearpath-financial/issues/79) | Nit | System dismissals read "Dismissed by Someone" | hosted |
| [#80](https://github.com/SpencerPresley/clearpath-financial/issues/80) | Nit | "Can't record placement an item that is needs rereview." | local |
| [#81](https://github.com/SpencerPresley/clearpath-financial/issues/81) | Nit | Removing your own Admin role says "Deactivate them instead" | local |
| [#82](https://github.com/SpencerPresley/clearpath-financial/issues/82) | Nit | Shortcuts dialog key caps run into the description | local |
| [#83](https://github.com/SpencerPresley/clearpath-financial/issues/83) | Nit | Unknown routes render a bare "Not Found" | hosted |
| [#84](https://github.com/SpencerPresley/clearpath-financial/issues/84) | Nit | No CSP on the SPA; `/favicon.ico` and `/robots.txt` return S3 403 XML | hosted |
| [#85](https://github.com/SpencerPresley/clearpath-financial/issues/85) | Nit | Add placement dialog: no field spacing, one error at a time | local |
| [#86](https://github.com/SpencerPresley/clearpath-financial/issues/86) | Nit | Library rows highlight on hover but only the title opens the item | hosted |

I didn't re-file anything already open (#53 red destructive buttons, #54 AI check/review naming, #55 Pull/Withdrawn, #56 decision forms push content down, #57 diff insertion style, #58 ISO dates in backend text). I saw all six again; they're unchanged.

## Walkthrough 1, rechecked

**Fixed, each verified by running the flow:**
- **B1:** after publishing PL terms v3 with CP-7 still drifted, CP-7's bar offers only Check now and Pull. Its banner says "fast-track it once the page is restored". Bulk reported "Fast-track 5 re-reviews" for 8 selected and left CP-7, CP-23 and CP-16 alone.
- **B2:** the "as low as 5.99%" suggestion reads "APRs from 10.49% to 35.99%", taken from the current terms.
- **B3:** CP-10's resubmit page says "Expired Oct 18, 2026 when personal loan offer terms v2 took effect. v3 has the new numbers…".
- **B4:** after fast-tracking CP-2 v5, both Findings and the decision record say "Carried from v3".
- **Should-fix items:**
  - S1: signing out on CP-7 and in as Priya lands on `/mine`.
  - S3: Details has a Decision record block with terms, rule set, engine, AI provenance and evidence.
  - S4: Waiting >3 days stayed at 11 across the publish.
  - S6: marketers see "AI review didn't run; your reviewer will check this by hand."
  - S7: Metrics has a role gate.
  - S8: ⇧A, ⇧R, ⇧X and J, the next item.
  - S14: "Live page vs approved v3" in the center pane.
  - S15: 178 already-imported rows collapse into one line.
  - S16: Users, the availability toggle and workload.
  - S17: "Last round: changes requested on v2…".
  - S18: reset clears and lands on Import with a "Demo reset · 44 items seeded" notice.
  - S20: CP-40 gets the stale-rate finding after the publish.
- **Nits:** Nit 13 is fixed; the assistant says "Assistant isn't available on this server" before you type.

**Partly fixed:**
- S19: the Library is right, but other screens still show expired legacy approvals as Approved (#68).
- S11: Apply exists only for single-value suggestions such as "10.49%".
- S5: the banner still says "Live copy changed" when the copy is *missing*.

**Still present, not re-filed (low):**
- Nit 4: the fast-track reason isn't prefilled.
- Nit 12: Sep decisions record engine `2026-10-24.5`.
- Nit 3: titles and assignee names truncate at 1280. "Rachel O…" appears even with no drawer open.
- Nit 17: small hit areas. The assistant panel's New thread and Close are 28×28 and Send is 50×28.

## Permission probes, local, from each role's own session

- **Marketer:**
  - Placement record, edit, check and takedown on Jordan's item: 403 with the rule named.
  - Demo partner-page edit, create user, export, comment on another marketer's item, risk edit, claim, demo reset, workload: 403.
  - `PATCH /api/me {roles:["admin"]}`: 200, but `roles` is ignored and stays `["marketer"]`.
  - Evidence pack of another marketer's item: 202, which matches the ruling that evidence is readable by anyone who can read the item.
- **Reviewer:** placement record and edit on someone else's item, demo page edit, create or patch user, demo reset, import sample: 403. `/me` role escalation is ignored.
- **Lead:** create or patch user, import sample, demo reset: 403.
- **Admin:** decide and claim return 403 ("needs the reviewer role").
- **Side observation, not a leak:** with an incomplete body, a few endpoints (terms publish, bulk fast-track, partner create) return 422 before 403, so a caller without the role learns the schema. Walkthrough 1 confirmed the same endpoints return 403 with a valid body.

## Hosted vs local

- **Same:** text, assets and data on every screen compared.
- **Console:** no errors on any hosted screen apart from the two expected 401s before sign-in (`/api/me`, `/_allauth/.../session`).
- **Speed:** no API call over 1.5 s, and every page settled in about 2 s.
- **Static assets:** `/assets/*` is `immutable`, and `index.html` is `no-cache`, so a deploy reaches evaluators on the next load.
- **Demo partner pages:** `/demo-partners/{lendcompare,cardscout,budgetbee}/` return 200 in under 0.25 s. LendCompare serves the edited 7.99% and "Guaranteed approval" copy, as the demo intends.
- **Hosted-only differences** (#84): the SPA has no CSP, and `/favicon.ico` and `/robots.txt` are S3 403 XML.
- **CP-222:** shows "AI check finished · no suggestions" on hosted, so the reconciler ran the real model as docs/demo.md describes.

## Polish checklist (make-interfaces-feel-better)

Measured with `getComputedStyle` and `getBoundingClientRect` on the hosted queue at 1440×900, with the assistant open.

| Check | Result |
|---|---|
| No `transition: all` | Pass: 0 elements |
| Font smoothing | Pass: `antialiased` on body |
| Tabular numbers | Pass: stats strip, Age, metrics tiles |
| Minimum hit area 40×40 | Fail, as in walkthrough 1 Nit 17: assistant New thread and Close 28×28, Send 50×28, Threads 87×28 |
| Spacing groups a label with its control | Fail in the Add placement dialog (#85); pass elsewhere |
| Restraint (§5.6) | Pass: no sparkles, gradients or celebratory copy. The assistant's empty state is three plain prompts. |

## What works well

- **Drift, end to end, on a real fetch.**
  - CP-23: Simulate partner edit → Check now → **Missing** → Needs re-review, in under 10 s.
  - CP-32: a redesigned page that kept the approved words stays **Unchanged**.
  - CP-7: Restore → Check now → **Unchanged** → **Reaffirm v3** appears.
  - The center-pane "Live page vs approved v3" diff (shot 31) is the clearest view of the problem in the product.
- **The terms change.** The impact preview ("3 approved items quote v2; 3 will need re-review. 3 items already in re-review will get the new numbers", with partners and per-item lanes) and the confirm dialog match the outcome. The B1 guard holds in both single and bulk (shot 30).
- **New submission.** Five findings with citations appear within about 2.5 s of typing. "Submit anyway / Keep editing" is inline, and every suggestion now uses current terms (shot 32).
- **Decision record in Details:** outcome, approver, terms version, rule-set date, engine, AI provenance ("Carried from v3", "Ran on v1") and evidence. This is the "beats Excel" argument made visible.
- **Re-import preview:** "178 rows already imported from this tracker on Aug 17, 2026" in one line, with the two real tracker problems (a note row, a duplicate) explained (shot 33).
- **Users and availability:** inline add with field validation ("At least 12 characters"), last-admin protection, Leah's out-of-office icon, and deactivation reassignment with a reason on every event.
- **Placements (new, #66):** add, edit and confirm takedown work and refresh history and the banner ("Takedown confirmed for 1 placement"). Takedown has a red confirm dialog.
- **Errors and gates:** role gates for Queue, Metrics, Users and Import. Designed not-found pages for items and partners. The assistant explains up front why it's disabled with no key.
- **Notifications:** grouped Today / Earlier, the right icon per kind, and clicking a row opens the item and marks it read. Tested locally only.

## First 3 minutes per role

**Reviewer (Dana).** The queue explains itself: CP-7 and CP-2 in alert red-orange, then the high-risk items. CP-2's banner and "Compare with approved v3" make the terms story in two clicks, and ⇧A fast-tracks it. CP-7 is the moment that sells the product: the center pane shows 9.99→7.99 and "Subject to credit" → "Guaranteed" on the live page. But the Findings tab beside it says "all triaged", and the queue row says 0 findings (#75). An evaluator who asks "why is this first?" has to find the answer in Details. A mistyped URL lands on a bare "Not Found" (#83). If they open the board to see the team view, Claim on Samuel's card fails (#76).

**Compliance lead (Rachel).** Offer terms, the impact preview and the B1 guard are strong: bulk fast-track skips the drifted listing, and the dialog says "5 items" for 8 selected. The drift demo runs live and reads like real monitoring. Right after the bulk approve, the Workload line still names the old heaviest reviewer with the old load (#69). Partners → LendCompare lists two tracker approvals as green Approved that lapsed in May and August (#68). Clicking one opens a screen of grey skeletons (#67).

**Marketer (Priya).** My submissions puts CP-22 (changes requested) first and explains every row in one line. Resubmit, Start new round and New submission all work, and the code checks land before she stops typing, with suggestions in current terms. After approval, nothing tells her to record where the ad runs (#78). If she finds Details → Where it runs, she can tick "Check this page daily" with no address and believe the page is monitored (#70).

**Admin (Avery).** Import lands on the go-live job. Re-running the sample now says in one line that the rows are already in, which fixes walkthrough 1's weakest admin moment. Users is complete and safe at the edges. The admin path in docs/demo.md then sends them to Library → Legacy only, and every legacy row opens to a skeleton that never resolves, with the tracker history that the import preserved shown nowhere (#67). That is the one screen that turns "Migration is proven" (spec §2) into a question. The Reset dialog's "People and sign-ins stay" (#71) also contradicts what reset does to the people they just added.
