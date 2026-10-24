# Drift monitor and fetch from URL (workstream M): report

Branch `wsM/drift`, PR #37, closes #14. Plan: `docs/plan/drift-monitor.md`. Review with resolutions:
`docs/plan/reviews/drift-monitor.md`. Screenshots: `docs/plan/reviews/ui/drift/`.

Executed natively (one implementer, TDD per task), then one fresh security-minded reviewer over the whole branch.

## What shipped

| Area | Where | Notes |
|---|---|---|
| SSRF-guarded fetcher | `backend/drift/fetcher.py` | pinned IP, explicit deny list, per-hop redirect validation, caps; every refusal tested |
| Visible text | `backend/drift/extract.py` | BeautifulSoup + stdlib `html.parser`; hidden/script/style/embeds dropped; one block per line |
| Copy locator | `backend/drift/compare.py` | verbatim → unchanged; else rapidfuzz alignment → page lines → word diff; score = how much of the copy survives; missing below 60 |
| Checks | `backend/drift/services.py`, `tasks.py` | Snapshot pending → running → succeeded / failed; reopen on drift; sweep 07:00 UTC; reconcile every 5 min |
| Reads + API | `backend/drift/selectors.py`, `api.py`, `schemas.py` | `GET /items/{id}/drift`, `POST /placements/{id}/drift-checks` (202), demo `GET/PUT /demo/partner-pages` |
| fetch-url | `backend/reviews/api.py` → `backend/drift/intake.py` | async ninja operation, 20/min per user, 422 on `url` with `details.reason` |
| Demo pages | `backend/drift/demo.py`, `views.py`, `urls.py`, template | `/demo-partners/{lendcompare,cardscout,budgetbee}/`, banner, noindex, never cached |
| Model | `reviews.Snapshot` + `reviews/0008_snapshot_drift.py` | one in flight per placement (partial unique), result iff succeeded, failure has a code |
| Infra | `infra/main/edge.tf` | `/demo-partners/*` → app origin (not applied; deploy wave) |
| Frontend | `features/submit/FetchFromUrl.tsx`, `features/review/Placements.tsx` | Fetch control restored; "Where it runs" in the Details tab |

## Decisions (and why)

- **fetch-url is async; "Check now" is a Celery job.** Under ASGI, Django runs every sync view *and every
  `MiddlewareMixin` hop* via `sync_to_async(thread_sensitive=True)` (`django/utils/deprecation.py:447`), i.e. on
  one thread per process. A sync view fetching `/demo-partners/...` from its own process holds that thread while
  the inbound request for the page waits for it: a deadlock until the fetch times out (dev runs 1 uvicorn worker,
  prod 2, so prod fails about half the time). Verified live after the change: fetch-url of
  `http://localhost:8000/demo-partners/budgetbee/` against a single-worker uvicorn returned in ~90 ms.
- **Pinning mechanism: `sni_hostname` request extension + `Host` header, URL host = checked IP.** Documented in the
  httpx docs (ctx7 `/encode/httpx`, advanced/extensions "sni_hostname") and verified in the installed httpcore2:
  `_async/connection.py:100,136` uses it as the TLS `server_hostname`. Live sanity check (manual, not a test):
  `https://example.com/` fetched OK through the pin; `https://wrong.host.badssl.com/` refused (cert mismatch still
  caught). The alternative, a custom httpcore `NetworkBackend`, isn't exposed by `httpx2.HTTPTransport` and would
  mean replacing a private `_pool`.
- **httpx2, not httpx.** The project already ships httpx2 2.16 (pydantic's maintained fork; `anthropic` depends on
  it); it's now an explicit main dependency (moved out of the dev group).
- **beautifulsoup4 + `html.parser` over selectolax.** Both maintained (selectolax 1.0.2, 2026-10-22; bs4 4.15,
  2026-06-07; checked on PyPI). The stdlib parser keeps native code off attacker-controlled HTML; speed doesn't
  matter at a few pages a day (1 MB parses in well under the test's 3 s bound).
- **Compare with the item's latest approved version**, not `Placement.approved_version` (set once at
  `record_placement`). After a terms fast-track the partner should show v+1: comparing to v2 would flag the
  corrected page and pass a page still quoting the superseded rate. Snapshots record `compared_version`.
- **Reopen only when** modified/missing, item `approved`, not legacy, placement live. Other statuses record the
  check and event only. Fetch failures are `failed` (with a code), never `missing`.
- **Verbatim copy with extra text around it is `unchanged`.** The copy as approved is intact; what the partner put
  next to it is the page code checks' job (shown as "new on the page").
- **Demo pages at `/demo-partners/`, not under `/api/`.** They stand in for third-party HTML pages; under `/api/`
  they'd be ninja operations in `ninja.json`. Cost: one CloudFront path pattern and one Vite proxy line. In
  production the worker fetches the public CloudFront URL (`DEMO_PARTNERS_BASE_URL`, default `FRONTEND_BASE_URL`)
  through the same guard; only dev allowlists exact local origins.
- **Demo switch state in the shared cache**, not a model: web (serves the page) and worker (fetches it) both see
  Redis; a flush only resets the demo to "original". `drift.demo.reset_demo_pages()` is for L's Reset demo.
- **Snapshot stays in `reviews`** (Foundation's placeholder; never written), extended by `reviews/0008`.

## Interfaces for others

```python
# L (demo seed): create an approved affiliate item whose approved copy is the page's copy, then:
drift.demo.PAGES  # slug, partner, item_title, product, copy, edited_copy, expected
drift.demo.seed_placement(*, actor, item_id, slug, clock) -> int    # monitored, open-ended placement on the page
drift.demo.reset_demo_pages() -> None                                # for POST /admin/demo/reset
# Anyone sending an item back for drift:
reviews.rereview.reopen_item(..., snapshot_id: int | None = None)    # ITEM_REOPENED.payload.snapshot_id (omitted when None)
# Drift reads (K's tools, if wanted):
drift.selectors.item_drift(*, item_id, clock) -> ItemDrift
```

## Shared-file edits (all additive)

- `backend/core/domain.py`: `DriftTrigger`; `EventType.DRIFT_CHECK_REQUESTED`, `DRIFT_CHECKED`.
- `backend/audit/payloads.py`: `DriftCheckRequestedPayload`, `DriftCheckedPayload`; `ItemReopenedPayload.snapshot_id`
  (excluded from the dump when None, so existing reopen events keep their shape and E's/F's tests are untouched).
- `backend/reviews/rereview.py`: `reopen_item(snapshot_id=None)`.
- `backend/reviews/models.py` + migration `0008` (Snapshot only).
- `backend/reviews/api.py`: the fetch-url stub replaced; `STUB_ERRORS`/`NotImplementedYet` imports dropped.
- `backend/config/{api.py,urls.py}`, `config/settings/{base.py,dev.py}` (app, beat entries, `DRIFT_FETCH_PRIVATE_ORIGINS`,
  `DEMO_PARTNERS_BASE_URL`), `config/tests/test_contract.py` (tags `drift`, `demo`; fetch-url out of the stub list;
  the "stub validates first" test now uses `POST /admin/users`).
- `backend/pyproject.toml` / `uv.lock`: `httpx2` (moved to main), `beautifulsoup4`, `rapidfuzz` — **likely
  `uv.lock` conflict with K/L; resolve by re-running `uv lock`.**
- `.env.example`: `DEMO_PARTNERS_BASE_URL` (commented).
- `infra/main/edge.tf`: one path pattern.
- Frontend: `features/review/tabs.tsx` (mount), `historyText.ts` (2 cases), `ui/icons.ts` (3 drift glyphs),
  `theme/theme.css` (placement/drift and restored fetch-url classes), `vite.config.ts` (proxy).

## Review

One fresh security-minded reviewer over the whole branch (`docs/plan/reviews/drift-monitor.md`): no SSRF bypass
found; one Critical and two Important, all fixed with tests:

- **C1**: a page declaring `charset=punycode` stalled the event loop (300 KB → 12 s, past the deadline, which only
  fires at an `await`). Charsets are now limited to web text encodings.
- **While fixing C1** I measured the parser on hostile shapes and found a second CPU sink: `"<div>" * 80_000`
  (400 KB) took 73 s in extraction, because each block's `insert_before/after` walks to the last descendant.
  Extraction is now one non-mutating pass (0.37 s).
- **I1**: `charset=idna` raised a raw `UnicodeError` (a 500). **I2**: `dns_failed` vs `address_not_allowed` let
  any user map VPC-only names; both are now `host_not_reachable` with one message. **I3**: one pool across redirect
  hops; now a client per hop.
- Minors fixed: IPv6 ranges, the dev allowlist (now `/demo-partners/` paths only and ignored unless `DEBUG`),
  TLS failures as their own permanent code, Check now throttled (10/min, own scope), `http_status` on the failed
  event. Deferred: M4 (reconciler measures "lost" from `requested_at`; duplicate enqueues are no-ops).

## Verification

- After merging main (J's screens, metrics; one conflict in `config/tests/test_contract.py`, where each side had
  removed its own stub): backend `pytest` 1608 passed (drift: 175); ruff, ruff format, pyrefly (`--group
  typecheck`) clean; no missing migrations; schema and client regenerated with no diff.
- Frontend: typecheck, eslint, prettier clean; vitest 563 passed.
- CI on PR #37 green at `e008c11` and re-run on the final head (Backend CI, Frontend CI incl. e2e unit, API contract `drift`, semgrep).
- Live (dev stack, one uvicorn worker): fetch-url of the BudgetBee demo page fills the form in ~90 ms (no
  self-deadlock); `169.254.169.254` refused; `1.2.3.4` times out with a message. Drift: unchanged → Simulate edit →
  Check now → modified with a diff and the item reopened (`drift_detected`, reassigned); CardScout → missing; a
  `.invalid` placement → failed. Screenshots in `docs/plan/reviews/ui/drift/`, captured before the review fixes:
  a host name that doesn't resolve now reads "That address can't be fetched: its name doesn't lead to a public
  website." instead of "That site's name didn't resolve." (`placement-missing-and-failed*`); IP-literal refusals
  are unchanged.

## Limitations and open risks

- Static HTML only: copy injected by client-side JavaScript isn't seen (documented in `fetcher.py`, `intake.py`,
  and the fetch-url 422 message for empty pages).
- Page-wide code checks are noisy by nature (other offers on the page trip rules); they are shown, marked new or
  not, and never reopen by themselves (decision below).
- Compose dev: the worker container can't reach `localhost:8000`; set `DEMO_PARTNERS_BASE_URL=http://web:8000` for
  the seed under compose (allowlisted in dev), or run the worker natively.
- `infra/main/edge.tf` needs the deploy-wave `terraform apply`; until then production has no `/demo-partners/*`.
- There's still no UI to record placements (only API and the seed); the Details panel shows them.
- The reconciler measures "lost" pending checks from `requested_at` (review M4): under a backlog over 10 minutes it
  re-enqueues every 5 minutes (no-ops) and fails checks queued over an hour as `stuck`.

## Decisions needed

1. **Should a check that finds the copy unchanged but new blocking code findings on the page reopen the item?**
   Today it doesn't: findings are shown (marked "new on the page") but only modified/missing reopen. Reopening on
   page-wide findings would reopen on any other offer the partner runs on the same page.
2. **Is "approved copy intact, partner text added beside it" = unchanged right?** That's the current rule (tested);
   the added text surfaces only through the page code checks.
3. **404/410 count as a failed check, not missing.** A page that's gone is arguably "missing". Current behaviour
   avoids reopening on a transient outage or a moved URL; the alternative is treating 404/410 as missing after N
   consecutive failures.
4. **Evasion (review M8).** The bot identifies itself (`ClearPathComplianceBot/1.0`), and copy hidden by a
   stylesheet class still counts as visible, so a partner can cloak. Honest identification is my default; a
   browser-like UA is a product/ethics call worth a line in `decisions.md`.
5. **Merge order with K/L:** `uv.lock` will conflict (I add httpx2/bs4/rapidfuzz); re-run `uv lock`. L needs
   `drift.demo.seed_placement` for the seed and `reset_demo_pages()` in Reset demo, with item copy equal to
   `PAGES[slug].copy`.
6. **`terraform apply`** of the `/demo-partners/*` CloudFront route at the deploy wave.
7. Reaffirm stays available for `drift_detected` re-reviews (I's existing behaviour); confirm that's wanted.
