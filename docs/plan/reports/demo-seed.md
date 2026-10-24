# Demo seed and Reset demo (workstream L): report

Issue #13. Plan: `docs/plan/demo-seed.md`. Walkthrough for evaluators: `docs/demo.md`.

## What was built

- **`backend/demo/` app.**
  - `content/` is the catalog. It has 11 people, 10 partners with agreements, offer terms (personal loan v1→v3,
    card v1→v2) and 44 item stories. Each story is copy versions plus timed steps.
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
| Legacy items | 178 from `samples/` tracker, imported through `imports.services` the evening before; 33 matched to seeded partners |
| Products / channels | personal loan, card, mortgage prequal; email, SMS, paid social, paid search, display, direct mail, landing page, affiliate page, call script; CA-only and national; prescreen |
| Rule coverage | every code rule id fires at least once (asserted against `CODE_RULES`), plus ≥10 clean versions |
| Triage | ≥40 accepted, ≥40 dismissed with reasons, carried-forward dismissals, system dismissals on fast-track |
| AI | scripted findings on most versions; one item with the AI failed after 4 tries (529), so approval needs an override (CP-40); one pending (CP-222) |
| History | events backdated over ~10 weeks, ~880 events; 5 fast-track approvals, 1 reaffirm (which found the 2026-07-21 Reg B rule as a new finding) |
| Drift | CP-7, CP-23 and CP-32 run on the three partner pages ClearPath hosts (`drift.demo.PAGES`), placed via `drift.demo.seed_placement`; 4 checks recorded through `drift.services` on the pages' own HTML; LendCompare is left edited, so CP-7's re-review comes from a real *modified* check |
| People | Dana's queue holds 5; Rachel (lead) holds 3; Leah is out of office and her released queue left 2 unassigned |

Runtime is about 11 s on a laptop, from both the command and the UI button with a real worker.

## Verification

- Backend, after rebasing on `2f91e1d` (drift and assistant merged):
  - `pytest`: 1765 passed;
  - `ruff check`, `ruff format --check` and `pyrefly check` (0 errors) are clean;
  - `makemigrations --check` reports no changes;
  - the exported schema matches the committed one;
  - `make semgrep` reports 0 findings.
- Frontend, after the rebase:
  - `npm run test:run`: 636 passed;
  - `typecheck`, `lint`, `format:check` and `build` are clean.
- Demo tests (`backend/demo/tests/`, 37 in all):
  - the catalog is pure: rule coverage, AI quotes are substrings, steps are in order;
  - the seed runs on one committed DB per module and checks: status counts, an event per item, every rule
    persisted, triage states, AI run statuses, legacy counts, terms versions, every handler's receipts present
    and nothing enqueued to the real worker;
  - a failing reset changes nothing, and reset restores the same `{title: (pk, status)}` snapshot;
  - API: two `seed_demo` runs on an empty DB, an admin reset after which the admin is still signed in, the
    in-flight job is returned to a second request, non-admins get 403, failed and stale jobs are reported,
    and a job that started late is judged by its start.
- Full stack, run against a fresh database `clearpath_wsl`:
  - setup: migrate, `seed_demo`, then `seed_demo` again (no-op); runserver on 8017, Vite on 5183, and a Celery
    worker on a private Redis DB;
  - I signed in as each role and took screenshots at 1440×900 into `docs/plan/reviews/ui/demo/`: `reviewer`,
    `lead`, `marketer`, `admin`, `marketer-my-submissions`, `reviewer-fast-track-rereview`,
    `reviewer-ai-failed`, `lead-metrics`, `admin-reset-confirm`, `admin-reset-running`, `admin-reset-done`;
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

- **Tracker history overlaps native history (open decision, below).** The sample tracker (a fixed fixture,
  Nov 3 2025 – Oct 23 2026) runs right up to yesterday, so Metrics shows Excel and the tool in use side by side
  for the native ten weeks.
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

## Decision needed: the tracker's dates (item 4)

**The ask.**
- End the sample tracker the day before the tool's go-live, about 10 weeks before the seed clock.
- Totals unchanged.
- Go-live is a shared value relative to the seed clock, so a reset months later keeps the split.

**Why it can't be built as stated.** The generator (`scripts/generate_sample_tracker.py`) simulates on a fixed
calendar, and its random path depends on calendar dates:
- `submission_dates` buckets by calendar month (`MONTHLY_VOLUME`).
- `pick_theme` filters seasonal themes by `submitted.month` (line 1159): "Holiday Expenses" in months 11–12,
  "Back to School" in 7–8, "Tax Season" in 1–4.
- The holidays and the freeze window decide which days are workdays.
- Request IDs carry a per-year counter (`MCR-YY-nnn`, line 1145), and year-less dates are inferred from that
  prefix.

The three ways to satisfy part of the ask:

- **(a) Re-anchor the simulation to a go-live argument, and run it at reset time.**
  - The generator moves into the backend so the seed can call it. `scripts/` becomes a thin wrapper, because the
    image's build context is `backend/`.
  - The window becomes [go-live − ~50 weeks, go-live − 1 day], with seasons following real months.
  - Cost:
    - The row count can stay 178, but the status, issue and problem-row mix changes, so the README oracle and G's
      oracle tests change.
    - Those numbers also differ for every go-live date, so the seed's tests would assert ranges instead of exact
      counts.
    - It's the largest change, and it lands in G's oracle.
- **(b) Simulate as today, and shift only the rendered dates by whole weeks.**
  - Every total stays identical, and it also works at reset time.
  - Cost:
    - Seasonal campaigns render out of season (a 10-week shift puts "Holiday Expenses" in September).
    - Request IDs either collide across the shifted year boundary or carry the wrong year, which breaks the
      importer's year inference.
    - The "2026" note row lands in the wrong place.
- **(c) Re-anchor once, statically.**
  - Regenerate the committed tracker so it ends 2026-08-14, the day before a go-live 10 weeks back, with the seed
    importing it as today.
  - Exact split for a reset now. A reset N weeks later shows an N-week gap between the tracker's end and the
    tool's start, but never an overlap.
  - Cost: the README oracle and G's oracle tests change once, apart from the row count.

**Recommendation: (c).** The hosted demo's life is weeks, so a growing gap is tolerable, while (b) produces visibly
wrong content and (a) puts a moving target under G's oracle tests. If a reset months out really matters, (a) is
the only correct option.
