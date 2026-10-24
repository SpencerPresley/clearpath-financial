# Demo seed and Reset demo (workstream L): report

Issue #13. Plan: `docs/plan/demo-seed.md`. Walkthrough for evaluators: `docs/demo.md`.

## What was built

- **`backend/demo/` app.**
  - `content/` is the catalog. It has 11 people, 10 partners with agreements, offer terms (personal loan v1→v2,
    card v1→v2, both entered at go-live) and 44 item stories. Each story is copy versions plus timed steps.
  - `story.py` is the step DSL.
  - `runner.py` merges every step into one timeline and plays it through the real service functions, using a
    `FixedClock` set to each step's backdated instant. It drains the outbox in-process after each step and
    answers AI checks with a scripted model (`ai.py`, model `demo-seed`).
  - `reset.py`, in one transaction under an advisory lock:
    - TRUNCATEs the domain tables (RESTART IDENTITY);
    - upserts the people;
    - plays the catalog;
    - records a `demo.reset` event.

    The on-commit task seams are no-ops throughout.
- **`manage.py seed_demo [--reset]`.** Without `--reset` it's a no-op if items exist. `seed_demo_users` now
  upserts the same 11 people.
- **`POST /api/admin/demo/reset`** (202 + job) and **`GET /api/admin/demo/resets/{id}`**, admins only. The reset
  runs as the Celery job `demo.reset`. A second request while one is in flight returns that job. A job still in
  flight after 15 minutes is marked failed on the next read or request, so a lost message can't wedge the
  button.
- **Shell.** An admin-only **Reset demo…** in the account panel, a confirm alert dialog, then polling at 1 s.
  The dialog can be closed while the job runs (polling continues); "done" and "failed" each raise a toast and
  refetch every query.
- **`docs/demo.md`.** Logins and a five-minute path per role. **`.env.example`**: `DEMO_USER_PASSWORD`, empty
  means the documented one.

## What the seed contains

| | |
|---|---|
| Native items | 44: submitted 5, in review 9, changes requested 4, approved 14, rejected 3, needs re-review 4 (terms changed 2, approval expired 1, drift 1), expired 3, withdrawn 2 |
| Legacy items | 178 from the `samples/` tracker (2025-09-02 to 2026-08-14), imported through `imports.services` (replayed the evening before so native items keep their CP keys, recorded at 08:30 on go-live, `TRACKER_IMPORTED`); 36 matched to seeded partners |
| Products / channels | personal loan, card, mortgage prequal; email, SMS, paid social, paid search, display, direct mail, landing page, affiliate page, call script; CA-only and national; prescreen |
| Rule coverage | every code rule id fires at least once (asserted against `CODE_RULES`), plus ≥10 clean versions |
| Triage | ≥40 accepted, ≥40 dismissed with reasons, carried-forward dismissals, system dismissals on fast-track |
| AI | scripted findings on most versions; one item with the AI failed after 4 tries (529), so approval needs an override (CP-40); one pending (CP-222) |
| History | 905 events, all from go-live (2026-08-17) on; 5 fast-track approvals; no seeded reaffirm (the guide's CP-7 path makes one) |
| Drift | CP-7, CP-23 and CP-32 run on the three partner pages ClearPath hosts (`drift.demo.PAGES`), placed via `drift.demo.seed_placement`; 4 checks recorded through `drift.services` on the pages' own HTML; LendCompare is left edited, so CP-7's re-review comes from a real *modified* check |
| People | Dana's queue holds 5; Rachel (lead) holds 3; Leah is out of office and her released queue left 2 unassigned |

Runtime is about 11 s on a laptop, from both the command and the UI button with a real worker.

## Verification

- Backend, after rebasing on `cdc026f` (#41 and #42 notifications inbox merged):
  - `pytest`: 1803 passed;
  - `ruff check`, `ruff format --check` and `pyrefly check` (0 errors) are clean;
  - `makemigrations --check` reports no changes;
  - the exported schema matches the committed one;
  - `make semgrep` reports 0 findings.
- Frontend, after the rebase:
  - `npm run test:run`: 673 passed;
  - `typecheck`, `lint`, `format:check` and `build` are clean.
- Demo tests (`backend/demo/tests/`, 45 in all):
  - the catalog is pure: rule coverage, AI quotes are substrings, steps are in order;
  - the seed runs on one committed DB per module and checks: status counts, an event per item, every rule
    persisted, triage states, AI run statuses, legacy counts, terms versions, every handler's receipts present
    and nothing enqueued to the real worker;
  - a failing reset changes nothing, and reset restores the same `{title: (pk, status)}` snapshot;
  - native history starts at go-live, after the tracker ends (item 4);
  - the seed sends no email: no `OutboxEmail` rows. #40's attention notifications (`PAGE_FINDINGS_FLAGGED`) are
    in-app `Notification` rows written by an outbox handler, delivered in-process like the rest, and the seed
    has no unchanged-copy-with-new-findings check that would raise one;
  - the guide's CP-7 path: Reaffirm is refused (`DriftNotRestored`) while the page differs, then Restore,
    a manual check (*unchanged*), and Reaffirm approves it. The test rolls back and re-edits the page;
  - API: two `seed_demo` runs on an empty DB, an admin reset after which the admin is still signed in, the
    in-flight job is returned to a second request, non-admins get 403, failed and stale jobs are reported,
    and a job that started late is judged by its start.
- Full stack, run against a fresh database `clearpath_wsl`:
  - setup: migrate, `seed_demo`, then `seed_demo` again (no-op); runserver on 8017, Vite on 5183, and a Celery
    worker on a private Redis DB;
  - I signed in as each role and took screenshots at 1440×900 into `docs/plan/reviews/ui/demo/`: `reviewer`,
    `lead`, `marketer`, `admin`, `marketer-my-submissions`, `reviewer-fast-track-rereview`,
    `reviewer-ai-failed`, `lead-metrics`, `admin-reset-confirm`, `admin-reset-running`, `admin-reset-done`;
  - after the re-anchor and #40, the data- and drift-dependent shots were retaken by a Playwright script on a
    fresh seed: `reviewer`, `lead`, `marketer`, `admin`, `reviewer-fast-track-rereview`, `reviewer-ai-failed`,
    `reviewer-drift-cp7` (now **Check now** / **Pull**), `lead-offer-terms` (v1→v2 from go-live), `lead-metrics`
    (imported bars end the week of Aug 10; native starts Aug 17), `lead-partners`, and the new
    `reviewer-drift-cp7-restored` (as Rachel; the page buttons are lead/admin). That last one is the guide's path run live: Restore original page, Check now
    through the real worker (*unchanged*), and **Reaffirm v3** appears;
  - #42's inbox on a fresh seed, opened for each login:
    - every notification carries its event's backdated time;
    - none is self-sent, and none is about a legacy item;
    - anything older than two days is marked read by the reset (`UNREAD_WINDOW`);
    - the unread ones are current: Dana 1 (CP-24 back for review), Sam 1, Nikhil 3 (new assignments);
    - Rachel has 2 old mentions, Priya 19 decisions and re-reviews, admin none.

    One product quirk shows here but isn't the seed's: a re-review gives the assignee two rows at the same instant,
    "needs re-review · offer terms changed" (`notify_rereview`) and "is back for your review" (the sticky
    re-assignment, `notify_assignee`);
  - I clicked Reset demo as admin while a marketer was also signed in: the job finished in about 10 s, a toast
    reported 42 items (44 since the drift stories), and both sessions survived.

## Fixed from the walk-through

- **The lead's first screen was an empty queue.** Rachel now carries three items herself: the card prescreen
  (needs the issuer's sign-off), a rush refi postcard, and a fast-track.
- **The marketer login had nothing to resubmit.** All four changes-requested items belonged to other marketers.
  CP-22 (card paid social) is now Priya's.
- **A lost reset job wedged the button.** The local macOS prefork pool crashed after taking the message, and the
  row stayed `queued` with nothing to run it. For 15 minutes every POST returned the dead job, and the GET said
  `queued` forever. Now stale in-flight rows are marked failed on read and on request (`STALE_MESSAGE`), with
  tests. The reset is one transaction, and the task's hard limit is 300 s, so a job past 15 minutes is dead and
  changed nothing.
- **Running reset jobs were misjudged as stale.** A job that waited in the queue and then started was judged
  by `requested_at`, and could be marked failed mid-run. Running jobs are now judged by `started_at`. A queued job
  that's abandoned and delivered late finds itself failed and doesn't run.
- **The dialog trapped the admin while the job ran.** It now closes freely. Polling continues, and the result
  arrives as a toast.

## Deviations, and why

- **`draft` status is not seeded.** It's unreachable: intake has no drafts (E), and hand-inserting one would
  break the seed-through-services rule.
- **Demo email domain stays `@clearpath.demo`.** `SignIn.tsx`'s demo-account picker and the e2e fixtures use it.
- **Drift checks run on the pages' HTML without a fetch.**
  - The seed records drift checks through `request_check` → `claim` → `complete`, with the page rendered in-process
    by `drift.demo.render_page`. The view now uses that same function.
  - A real fetch isn't possible at seed time: on a first deploy `deploy.sh` seeds before `up`, tests have no
    server, and prod has no `/demo-partners/*` route until the deploy-wave apply.
  - *Check now* after the seed does fetch for real, through the worker.
- **The demo pages now quote the seeded offer.** M's `PAGES` copy said "7.49%" and "Issued by Lakeside Bank".
  Seeding an approval of that would mean approving copy that the terms and issuer rules flag against the seeded
  terms (PL floor 9.99%, Harborview Bank). The pages now carry the seeded items' approved copy, and the
  LendCompare edit lowers the floor to 7.99% and restores "Guaranteed approval".
  - The drift tests check outcomes per page generically, so they pass unchanged (175).
  - `reset_demo_pages` gained `edited=` so Reset can leave LendCompare edited.
- **The tracker import is seeded, at day −1.** That way the Library, Metrics and Import screens have legacy
  history on first login. It's a decision below.
- **Item keys follow seed order.** Natives are CP-1…CP-43, legacy CP-44…CP-221, and the pending item is CP-222,
  because it's submitted after the import in the timeline.
  - They're stable across resets (RESTART IDENTITY), but adding a story shifts every later key.
  - `docs/demo.md` cites keys, so `test_the_keys_the_guide_cites_are_the_items_it_describes` pins each one to its
    title.

## Risks and open questions

- **Tracker and native history no longer overlap** (item 4 below). A reset weeks from now opens a gap between
  the tracker's end and go-live; a test fails if they ever overlap.
- **CP-222 only stays pending for ~10 minutes.** At 10 minutes the reconciler re-enqueues the run on the real
  model. With an API key it gets a real review; without one it fails ("no Anthropic API key"). That's inherent
  to a pending check, and `docs/demo.md` says so.
- **Orphaned files on reset.** TRUNCATE doesn't delete attachment, import and export files from storage (local
  media or S3). Each reset leaves 14 small attachment files plus the import's xlsx. That's negligible for
  a demo, but a sweep would be a follow-up.
- **The assistant's checkpointer tables are wiped explicitly.** K's LangGraph state lives in non-model tables
  (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, from `assistant/0002_checkpointer`) keyed by the
  `AssistantThread` rows a reset truncates. `domain_tables()` now adds them, but keeps `checkpoint_migrations`
  (the library's schema record); a test pins both. A future non-model table would need the same treatment.
- **Deploy ordering: apply `edge.tf` before the first seeding deploy (blocking for the hosted demo).**
  - The three seeded monitored placements point at `<FRONTEND_BASE_URL>/demo-partners/<slug>/`, and the
    `/demo-partners/*` CloudFront behavior from #37 isn't applied yet.
  - Until it is, those paths fall to the default S3 behavior. There, `infra/main/functions/spa-rewrite.js` serves
    `/index.html` for any extensionless path: a 200 with no partner copy.
  - The next `drift-sweep` (07:00, `CELERY_BEAT_SCHEDULE`) would then record *missing*. That reopens CP-23 and
    CP-32 and overwrites CP-7's seeded state.
  - So the deploy-wave `terraform apply` of `edge.tf` (and the `DEMO_USER_PASSWORD` parameter) has to precede the
    first deploy that seeds, or at least that deploy's first 07:00 sweep.
- **The reset holds an advisory lock and truncates every domain table for ~10 s.** Requests in that window wait
  on the lock. Fine for a demo, and the reason it's admin-only.

## Settled with the orchestrator, and built

1. **Hosted password.**
   - Terraform generates `/clearpath/prod/DEMO_USER_PASSWORD`: a `random_password`, SecureString, 20 letters and
     digits. It follows the pattern of `DJANGO_SECRET_KEY`.
   - It isn't write-only, because evaluators have to be given it. `infra/README.md` ("Demo logins") shows how to
     read it.
   - `render-env.sh` refuses to deploy if it, `DJANGO_SECRET_KEY` or `POSTGRES_PASSWORD` is missing. I checked
     this with stubbed `aws` and `curl`.
   - Prod settings set `DEMO_PASSWORD_DEFAULT_ALLOWED = False`, and `demo_password()` then refuses an unset value
     or the published one. The check is where the password is used, not at settings import, because
     `deploy.yaml` runs `collectstatic` on prod settings with no app secrets.
   - A refused Reset demo shows the reason on the job.
2. **The tracker import stays seeded.**
3. **Seeding on start.**
   - `compose.yaml`'s web service runs `migrate && seed_demo && uvicorn`.
   - Prod doesn't migrate on container start: `deploy.sh` runs `migrate` as a one-off before `up`, and nothing else
     starts the stack (`user_data` only installs Docker). So `seed_demo` runs right after that step in
     `deploy.sh`, not in `compose.prod.yaml`.
   - Two reasons. A failed seed stops the deploy while the old containers still serve. And the first seed
     against RDS doesn't eat into the web healthcheck window (start 20 s + 6 × 10 s).
   - `compose.prod.yaml`'s header says where it happens.
5. **Landing route by role.**
   - The queue moved from `/` to `/queue`. `/` renders a `<Navigate replace>` to `landingFor(roles)`:
     - reviewer or lead → `/queue`;
     - marketer → `/mine`;
     - admin → `/import`;
     - no roles → `/library`.
   - With several roles, work comes first: a lead who is also an admin lands on the queue.
   - It's a component, not `beforeLoad`, because the viewer comes from `SessionGate`, so there's no sign-in race.
   - Updated: the nav, the Metrics "waiting" links, `QueuePage`'s route ID, and the unit, browser and e2e tests.
   - Separately, `e2e/shell.spec.ts` still asserted that reviewers don't see Offer terms. #36 changed that and CI
     doesn't run e2e, so it was already failing on main. It now asserts against Metrics, which is lead-only.

4. **The tracker ends the Friday before go-live (option (c): re-anchored once, statically).**
   - **Go-live is `demo/content/calendar.py` `GO_LIVE`: Monday 2026-08-17 08:00, `day(68)` from the seed clock.**
     The tracker's last date is Friday 2026-08-14. The orchestrator's "2026-08-14" assumed native history started
     10 weeks back. It didn't, and three things had to move to make that true:
     - **`mtg-social-spring`** was submitted 2026-04-19, because its paid-social approval needed six months to
       lapse into the seed's only Reaffirm. Expiry is `decided_at` + 6 months (`reviews/decisions.py`
       `approval_expiry`), and legacy items never re-review (`rereview.py` skips `is_legacy`), so the six-month
       story can't exist inside a ten-week window. It's now the first item through the app (CP-1, approved 8/18,
       running on Meta), and the Reg B 7/21 note moved to its first checklist. **Cost: the seed has no Reaffirm
       decision.** The Reaffirm lane is still demonstrated live: the guide's CP-7 path ends in one.
     - **Offer terms** were published 2025-11-03 (PL 8.99%, card) and 2026-06-01 (PL 9.49%). The go-live terms are
       now entered that morning: PL v1 at 9.49%, the floor the tracker's 6/1 rate sheet left, then v2 at 9.99% on
       day 6; card v1, then v2 on day 20. **PL history is v1→v2, not v1→v3**; the 8.99% era lives in the imported
       tracker, whose comments quote it.
     - **Partners** were entered 2026-04-07. They're now entered at go-live, or at 09:00 on their agreement date
       if that's later (BudgetBee signed 2026-09-14, so it's added then).
   - **Generator** (`scripts/generate_sample_tracker.py`):
     - AS_OF 2026-08-14;
     - submissions 2025-09-02 to 2026-08-12;
     - `MONTHLY_VOLUME` Sep 2025 to Aug 2026, still 178;
     - Labor Day 2025 added to the holidays;
     - the re-review window ends 8/12;
     - file created 2025-08-28.
     - Seasons, the freeze, the 6/1 rate change and the 7/21 Reg B rewrite are unchanged. The layout is unchanged
       too (note row r43, duplicate r64/r68, reused ID r121/r122).
     - `SEED` is now 20250908. With the old seed the new calendar produced no five-round item and no clean
       "Not Started" status, so `mapping.py`'s `"not started"` entry would have lost its only exercise. I picked the
       first of twelve candidate seeds that kept both and every README bullet non-empty.
   - **New totals** (`samples/README.md`):

     | | Before | Now |
     |---|---|---|
     | Items / distinct IDs / rows | 178 / 177 / 180 | same |
     | Submitted range | 2025-11-03 to 2026-10-20 | 2025-09-02 to 2026-08-12 |
     | Last updated | 2026-10-23 | 2026-08-14 |
     | approved / approved_with_edits | 132 / 13 | 125 / 14 |
     | changes_requested / in_review / submitted / rejected | 11 / 8 / 8 / 6 | 10 / 12 / 8 / 9 |
     | Open / unassigned | 16 / 8 | 20 / 8 |
     | Rows with a partner, after import | 33 | 36 |
     | Asset links: hyperlink / text URL / none | 112 / 45 / 22 | 96 / 58 / 25 |
     | Placement links: hyperlink / text URL | 23 / 72 | 7 / 87 |

   - **G's oracle tests**: `imports/tests/test_normalize.py`, `test_services.py`, `test_api.py`, `test_workbook.py`
     and `exports/tests/test_exports.py`.
     - The numeric totals above changed.
     - Hard-coded rows were re-pointed at rows that have the same property: the note row 19 → 43, the reused ref
       `MCR-26-101-b` → `MCR-26-077-b`, the "Pending" row, the "Lend Compare" rows, the year-crossing row, and the
       approval-before-submission date (10/1/25 → 8/1/25, since row 2 is now submitted 2025-09-02).
     - `test_legacy_item_fields` used one row (MCR-25-012) that was both approver-only and blank-expiry. No row is
       both now, so it checks one row per property: approver-only, blank expiry, blank status, text expiry,
       "CardPerks".
     - No assertion was removed. `docs/plan/import-export.md` and `reports/sample-tracker.md` still quote the old
       numbers as history.
   - **Overlap guard.** `test_native_history_starts_at_go_live_after_the_tracker_ends` asserts:
     - the latest legacy `submitted_at` / `approved_at` is 2026-08-14 and before `GO_LIVE`;
     - the first event in the database is exactly at `GO_LIVE`;
     - no native item is submitted before it.

     I checked it fails: with `GO_LIVE` moved to `day(80)` it fails with `2026-08-14 < 2026-08-05`. A story step
     placed before go-live fails the first-event assertion.
   - **Seeded later?** A reset N weeks after 2026-10-24 shows an N-week gap between the tracker and go-live, never
     an overlap.
