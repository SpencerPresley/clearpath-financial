# Demo seed and Reset demo (workstream L): report

Issue #13. Plan: `docs/plan/demo-seed.md`. Walkthrough for evaluators: `docs/demo.md`.

## What was built

- **`backend/demo/` app.**
  - `content/` is the catalog. It has 11 people, 8 partners with agreements, offer terms (personal loan v1→v3,
    card v1→v2) and 42 item stories. Each story is copy versions plus timed steps.
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
| Native items | 42: submitted 5, in review 9, changes requested 4, approved 12, rejected 3, needs re-review 4 (terms changed 2, approval expired 1, drift 1), expired 3, withdrawn 2 |
| Legacy items | 178 from `samples/` tracker, imported through `imports.services` the evening before; 33 matched to seeded partners |
| Products / channels | personal loan, card, mortgage prequal; email, SMS, paid social, paid search, display, direct mail, landing page, affiliate page, call script; CA-only and national; prescreen |
| Rule coverage | every code rule id fires at least once (asserted against `CODE_RULES`), plus ≥10 clean versions |
| Triage | ≥40 accepted, ≥40 dismissed with reasons, carried-forward dismissals, system dismissals on fast-track |
| AI | scripted findings on most versions; one item with the AI failed after 4 tries (529), so approval needs an override (CP-38); one pending (CP-220) |
| History | events backdated over ~10 weeks, ~880 events; 5 fast-track approvals, 1 reaffirm (which found the 2026-07-21 Reg B rule as a new finding) |
| People | Dana's queue holds 4; Rachel (lead) holds 3; Leah is out of office and her released queue left 2 unassigned |

Runtime is about 11 s on a laptop, from both the command and the UI button with a real worker.

## Verification

- Backend, after rebasing on `64c7fb6`:
  - `pytest`: 1459 passed;
  - `ruff check`, `ruff format --check` and `pyrefly check` (0 errors) are clean;
  - `makemigrations --check` reports no changes;
  - the exported schema matches the committed one;
  - `make semgrep` reports 0 findings.
- Frontend, after the rebase:
  - `npm run test:run`: 460 passed;
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
    reported 42 items, and both sessions survived.

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
- **Drift is simulated.** CP-7's drift uses `reopen_item(reason=drift_detected)`, which stands in for M's
  snapshot-diff detector. When M lands, the story can switch to a real snapshot pair.
- **The tracker import is seeded, at day −1.** That way the Library, Metrics and Import screens have legacy
  history on first login. It's a decision below.
- **Item keys follow seed order.** Natives are CP-1…CP-41, legacy CP-42…CP-219, and the pending item is CP-220,
  because it's submitted after the import in the timeline. `docs/demo.md` cites these keys, and they're stable
  across resets (RESTART IDENTITY).

## Risks and open questions

- **Tracker history overlaps native history.** The sample tracker (a fixed fixture, Nov 3 2025 – Oct 23 2026)
  runs right up to yesterday, so Metrics shows Excel and the tool in use side by side for the native ten weeks.
  It reads as a pilot period, which is defensible. If not, the fix is in `scripts/generate_sample_tracker.py`
  (end its dates ~10 weeks back), not in L.
- **CP-220 only stays pending for ~10 minutes.** At 10 minutes the reconciler re-enqueues the run on the real
  model. With an API key it gets a real review; without one it fails ("no Anthropic API key"). That's inherent
  to a pending check, and `docs/demo.md` says so.
- **Orphaned files on reset.** TRUNCATE doesn't delete attachment, import and export files from storage (local
  media or S3). Each reset leaves 14 small attachment files plus the import's xlsx. That's negligible for
  a demo, but a sweep would be a follow-up.
- **Only Django-model tables are wiped.** `domain_tables()` comes from `apps.get_models()`. If K's LangGraph
  checkpointer keeps its own non-model tables, a reset leaves old assistant threads behind; those would need
  adding to the TRUNCATE list.
- **Finding for J: marketer and admin land on a page that isn't in their nav.** The index route sends every
  role to the Queue (`/?view=mine&status=…`). Queue isn't in the marketer's or admin's nav, so their first
  screen is an empty queue they can't get back to (`marketer.png`, `admin.png`). The marketer should land on
  **My submissions**. `docs/demo.md` describes what happens today; I didn't change the route because it isn't
  L's file.
- **The reset holds an advisory lock and truncates every domain table for ~10 s.** Requests in that window wait
  on the lock. Fine for a demo, and the reason it's admin-only.

## Decisions needed

1. **The documented default password `ClearPath-demo-2026` is in code** (`demo/users.py`) and used when
   `DEMO_USER_PASSWORD` is unset. On the hosted demo that means anyone who reads the repo can sign in as admin
   and press Reset. The alternative is to set `DEMO_USER_PASSWORD` in the deploy's secrets and publish it
   alongside the URL. That costs one more secret, and `docs/demo.md` already reads "or the deployment's".
   Recommendation: set it on the hosted deploy. The admin can wipe everything there, and a published password
   in a public repo is effectively public.
2. **Seeding the tracker import vs leaving it for the admin.** It's seeded now, so Metrics and the Library have
   history from the first click. The cost: the admin's Import screen shows a finished import instead of an
   empty state to try the flow. They can still upload `samples/` again, which skips rows already imported (by tracker ID).
3. **`seed_demo` on deploy.** Nothing in `infra/` runs it today, so a fresh deploy has no demo until someone
   runs the command or clicks Reset. Options:
   - (a) a one-off `seed_demo` step in the deploy runbook, which is idempotent and does nothing if data exists;
   - (b) run it in the container entrypoint after migrate. This is also safe, because it's a no-op when items
     exist, but it adds ~11 s to the first boot.

   Recommendation: (b), since it is the no-op path on every boot after the first.
