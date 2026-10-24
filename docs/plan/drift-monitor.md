# Drift monitor and fetch from URL (workstream M, #14) Implementation Plan

> **For agentic workers:** executed natively (one implementer, one fresh security-minded reviewer over the whole
> branch at the end). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fetch affiliate pages safely from the server, prefill intake copy from a URL, and monitor live
placements for drift from the approved copy, reopening the item when the copy on the page changes or disappears.

**Architecture:** one SSRF-guarded async fetcher (`drift/fetcher.py`, httpx2 with the resolved IP pinned) used by
two callers: the async `POST /items/fetch-url` operation and the Celery drift check. Drift checks are Snapshot rows
(`reviews.Snapshot`, extended) moved pending → running → succeeded/failed by a Celery task, mirroring D's AI-check
pattern (`request` in the caller's transaction, enqueue on commit, `claim`, reconcile). Demo affiliate pages are plain
Django views under `/demo-partners/<slug>/`, with a lead/admin "Simulate edit" toggle in the shared cache.

**Tech stack:** httpx2 2.16 (already a runtime dependency through `anthropic`; made explicit), beautifulsoup4 4.15
with the stdlib `html.parser`, rapidfuzz 3.14, Celery beat, React + generated hooks.

**Spec:** `docs/product-spec.md` "Drift monitoring"; `docs/spec.md` §4.3 (stretch), §6; `docs/decisions.md` (no
whole-page diff); issue #14 brief.

## Global constraints

- Fetch only `http`/`https`, ports 80/443 (plus dev-allowlisted origins). No userinfo in URLs.
- Resolve DNS once per hop; refuse if **any** resolved address is denied; connect to the resolved IP (URL host =
  IP, `Host` header = hostname, `sni_hostname` extension = hostname, so TLS still verifies the hostname:
  `httpcore2/_async/connection.py:100,136`).
- Denied networks (explicit list, not `ipaddress.is_private`): 0.0.0.0/8, 10/8, 100.64/10, 127/8, 169.254/16,
  172.16/12, 192.0.0/24, 192.0.2/24, 192.168/16, 198.18/15, 198.51.100/24, 203.0.113/24, 224/4, 240/4,
  255.255.255.255; `::/128`, `::1/128`, `fc00::/7`, `fe80::/10`, `ff00::/8`, `2001:db8::/32`, `100::/64`;
  IPv4-mapped `::ffff:0:0/96`, NAT64 `64:ff9b::/96` and 6to4 `2002::/16` are unwrapped to their IPv4 and
  re-checked.
- `follow_redirects=False`; at most 5 hops, each fully re-validated. `trust_env=False` (no env proxies, no
  `.netrc`). Cookie jar cleared before every hop. `Accept-Encoding: identity`; a non-identity
  `Content-Encoding` is refused (no decompression bombs).
- Timeouts: connect 5 s, read 10 s, write 5 s, pool 5 s; 15 s total deadline across all hops.
- Body cap 2 MB counted on the bytes read (Content-Length checked first but not trusted).
- Content types: `text/html`, `text/plain` only.
- User-Agent: `ClearPathComplianceBot/1.0 (+drift monitor; compliance review of affiliate placements)`.
- Static HTML only, no JavaScript rendering (documented limitation).
- Tests never hit the network: resolver and transport are injected (`httpx2.MockTransport`).
- Fetch failures are never `missing`: they are `status=failed` snapshots with an error code; only a successful
  fetch can produce unchanged/modified/missing.

## Decisions taken here (and why)

- **fetch-url is an async ninja operation; "Check now" is a Celery job.** Under ASGI every sync view and every
  `MiddlewareMixin` hop runs on one shared thread per process (`django/utils/deprecation.py:447`,
  `thread_sensitive=True`). A sync view fetching `/demo-partners/...` from its own process would wait on itself until
  the timeout (dev runs 1 uvicorn worker, prod 2), and any inline fetch blocks every other request in that worker.
  The async operation awaits network I/O on the event loop; the worker process fetches drift pages.
- **Compare against the item's latest approved version**, not `Placement.approved_version` (set once at
  `record_placement`, never updated). After a terms fast-track the partner should show v+1; comparing to v2 would
  flag the corrected page and pass a page still quoting the superseded rate. The snapshot records
  `compared_version`.
- **Reopen only when** the result is modified/missing, the item is `approved`, not legacy, and the placement is live.
  Other statuses record the snapshot and event only.
- **Snapshot stays in `reviews`** (Foundation put it there for M; one `reviews/0008` migration extends it); the code
  lives in a new `drift` app with no models of its own.
- **Demo pages at `/demo-partners/<slug>/`, not under `/api/`**: they are HTML pages standing in for third-party
  sites, not API operations (an `/api/` route would land in `ninja.json` and the contract check). Cost: one path
  pattern in `infra/main/edge.tf` and one Vite proxy entry.
- **Demo toggle state in the Django cache** (Redis in dev/prod, shared by web and worker): no model, wiped by a
  Redis flush, which only resets the demo to "original".
- **beautifulsoup4 + `html.parser`** over selectolax: both are maintained (selectolax 1.0.2, 2026-10-22; bs4 4.15,
  2026-06-07); bs4 with the stdlib parser keeps a native parser off attacker-controlled HTML, and speed is
  irrelevant at a handful of pages a day.
- **Page code checks** run the engine on the page text with the compared version's `rule_context` (same product,
  channel, markets, partner, evidence kinds, current terms). Findings are stored on the snapshot as JSON, each marked
  `new` when its rule doesn't fire on the approved copy. They don't reopen by themselves (open question for Spencer).

## File structure

| File | Responsibility |
|---|---|
| `backend/drift/fetcher.py` | `fetch_page(url, *, resolver, transport, policy) -> FetchedPage`; `FetchError(code)`; the address policy |
| `backend/drift/extract.py` | `visible_text(html) -> PageText(title, text)` |
| `backend/drift/compare.py` | `normalize`, `compare(approved, page) -> Comparison(result, score, matched_text, diff)` |
| `backend/drift/services.py` | `request_check`, `claim`, `complete`, `fail`, `run_sweep`, `reconcile` |
| `backend/drift/selectors.py` | `item_drift(item_id, viewer, clock) -> ItemDrift` |
| `backend/drift/demo.py` | demo page content, cache-backed `is_edited/set_edited/reset_demo_pages`, `demo_slug_for(url)` |
| `backend/drift/views.py` + `templates/drift/partner_page.html` | the public demo pages |
| `backend/drift/api.py`, `schemas.py` | drift + demo routers |
| `backend/drift/tasks.py` | `drift.run_check`, `drift.sweep` (daily), `drift.reconcile` |
| `backend/drift/demo.py` `seed_placement` | a monitored placement on a demo page, for L's demo seed |
| `backend/reviews/models.py`, `migrations/0008_snapshot_drift.py` | Snapshot fields |
| `backend/reviews/api.py` | `fetch-url` becomes async and real |
| `frontend/src/features/submit/FetchFromUrl.tsx` | restored control |
| `frontend/src/features/review/Placements.tsx` | placements + last check + diff + Check now + Simulate edit |

Shared edits (additive): `core/domain.py` (2 EventTypes), `audit/payloads.py` (2 payloads; `ItemReopenedPayload`
gains `snapshot_id`), `reviews/rereview.py` (`reopen_item(snapshot_id=None)`), `config/settings/{base,dev}.py`,
`config/urls.py`, `config/api.py`, `config/tests/test_contract.py`, `pyproject.toml`/`uv.lock`,
`infra/main/edge.tf`, `frontend/vite.config.ts`, `features/review/tabs.tsx` (mount), `historyText.ts`,
`theme.css`.

## Review focus

1. Copy split across elements, `&nbsp;`, curly quotes, different line breaks → still `unchanged`
   (`test_compare_ignores_markup_and_whitespace`).
2. A page in ISO-8859-1 (charset in the header) decodes without mojibake; undeclared charset falls back to UTF-8
   with replacement (`test_fetch_decodes_declared_charset`).
3. A slow-drip server that sends a byte every 5 s → total deadline, `timeout` (`test_total_deadline`).
4. Double-click "Check now" → one in-flight snapshot, second call returns it (`test_request_check_is_idempotent`).
5. Item re-approved on v3 after drift → next check compares against v3 (`test_compares_latest_approved_version`).

---

### Task 1: SSRF-guarded fetcher

**Files:** create `backend/drift/{__init__,apps,fetcher}.py`, `backend/drift/tests/test_fetcher.py`; modify
`pyproject.toml` (main deps `httpx2`, `beautifulsoup4`, `rapidfuzz`), `config/settings/base.py` (`drift` app,
`DRIFT_FETCH_PRIVATE_ORIGINS: list[str] = []`), `dev.py` (allowlist `localhost:8000`, `127.0.0.1:8000`,
`localhost:5173`, `web:8000`), pyrefly includes.

**Interfaces (produces):**
```python
class FetchFailure(StrEnum): INVALID_URL, SCHEME_NOT_ALLOWED, PORT_NOT_ALLOWED, CREDENTIALS_IN_URL, DNS_FAILED,
    ADDRESS_NOT_ALLOWED, TOO_MANY_REDIRECTS, CONNECT_FAILED, TIMEOUT, HTTP_ERROR, CONTENT_TYPE_NOT_ALLOWED,
    ENCODING_NOT_ALLOWED, TOO_LARGE
class FetchError(Exception): code: FetchFailure; message: str; http_status: int | None; transient: bool
@dataclass(frozen=True) class FetchedPage: url: str; final_url: str; status: int; content_type: str; text: str
type Resolver = Callable[[str, int], Awaitable[list[str]]]   # default: loop.getaddrinfo
async def fetch_page(url: str, *, resolver: Resolver = system_resolver, transport: AsyncBaseTransport | None = None,
                     private_origins: Collection[str] | None = None) -> FetchedPage
def is_denied_address(ip: str) -> bool
```

- [ ] Tests (each a refusal or a guarantee): http/https only (`ftp://`, `file://`, `gopher://` → SCHEME);
  `https://u:p@host/` → CREDENTIALS; `:8080` → PORT; every denied network above incl. `169.254.169.254`,
  `100.64.0.1`, `::1`, `fe80::1`, `fd00::1`, `::ffff:127.0.0.1`, `64:ff9b::a9fe:a9fe`, `2002:7f00:1::` →
  ADDRESS; a resolver returning one public and one private address → ADDRESS; literal-IP URL checked the same way;
  pinned request (`request.url.host == "93.184.215.14"`, `headers["host"] == "partner.example"`,
  `extensions["sni_hostname"] == "partner.example"`); resolver called once per hop; redirect to
  `http://169.254.169.254/` → ADDRESS; 6 redirects → TOO_MANY; relative Location resolved against the current URL;
  Set-Cookie on hop 1 not sent on hop 2; no `Authorization`/`Cookie` header ever; UA set; `application/pdf` →
  CONTENT_TYPE; `Content-Encoding: gzip` → ENCODING; Content-Length 3 MB → TOO_LARGE; 3 MB streamed without length
  → TOO_LARGE; 404 → HTTP_ERROR not transient, 503 → transient; total deadline; charset decode; dev allowlist lets
  `localhost:8000` through only when listed, and the test/prod settings list is empty.
- [ ] Implement; run `uv run pytest drift -q`; commit.

### Task 2: Visible text and comparison

**Files:** `backend/drift/{extract,compare}.py`, tests.

**Interfaces:** `visible_text(html: str) -> PageText(title: str | None, text: str)` (drops script, style, noscript,
template, svg, iframe, head except title, `[hidden]`, `aria-hidden=true`, inline `display:none`; block elements
break lines; text capped at 100 000 chars). `normalize(text) -> str` (NFKC, curly quotes → straight, all whitespace
→ one space, strip). `compare(approved: str, page: str) -> Comparison(result: DriftResult, score: float,
matched_text: str, diff: tuple[DiffSegment, ...])`. Constants `MISSING_BELOW = 60.0`.

- [ ] Tests: exact copy inside nav/ads → unchanged, score 100; one rate changed → modified, diff
  `delete "7.49%" / insert "5.99%"` with no leading/trailing page noise; inserted sentence → modified; copy removed
  (page about loans, shared vocabulary) → missing; boundary tests at the threshold; 1 MB HTML parses under 2 s;
  10 000-deep nesting doesn't raise.
- [ ] Algorithm: `normalize` both; substring → unchanged. Else `fuzz.partial_ratio_alignment(approved, page)`;
  below threshold → missing. Else widen the page window by `max(40, len(approved)//4)` each side, snap to spaces,
  `diff_texts(approved, window)`, drop leading/trailing INSERT segments; `matched_text` = non-delete text.
- [ ] Commit.

### Task 3: Snapshot model, events, services, tasks

**Files:** `reviews/models.py` + `0008_snapshot_drift.py`; `core/domain.py` (`DRIFT_CHECK_REQUESTED =
"placement.drift_check_requested"`, `DRIFT_CHECKED = "placement.drift_checked"`, `DriftTrigger`); `audit/payloads.py`;
`reviews/rereview.py`; `drift/{services,tasks}.py`; beat entries in `base.py` (sweep 07:00 UTC daily, reconcile
every 5 min); tests.

Snapshot: `placement, status (CheckStatus), trigger, requested_by (null), requested_at, started_at, finished_at,
attempts, url, final_url, http_status, title, text, content_sha256, compared_version (null), result (null unless
succeeded), score, matched_text, diff (JSON segments), findings (JSON), error_code, error_message, reopen_event
(null)`. Constraints: one in-flight (pending/running) per placement (partial unique); `result` set iff succeeded.

```python
request_check(*, actor: User | None, placement_id: int, trigger: DriftTrigger, clock) -> int  # snapshot id
claim(*, snapshot_id, clock) -> Claim | None          # pending -> running, attempts += 1
complete(*, claim, page: FetchedPage, clock) -> SnapshotOutcome   # compare, page checks, event, maybe reopen
fail(*, claim, error: FetchError, clock) -> None
run_sweep(*, clock) -> SweepResult(requested, skipped)   # monitored, url set, live, item approved
reconcile(*, clock) -> ReconcileResult   # running > 10 min -> failed(stuck); pending > 10 min -> re-enqueue
```

- [ ] Tests: request writes pending + DRIFT_CHECK_REQUESTED and enqueues on commit; idempotent while in flight;
  refuses (409) without URL, not-live placements are still checkable manually; permission (owner, reviewer, lead,
  admin; another marketer 403); modified on approved live item → needs_rereview(drift_detected), sticky to the
  approver, ITEM_REOPENED payload carries `snapshot_id`, snapshot links `reopen_event`; missing → same; unchanged →
  no transition; modified on needs_rereview item → snapshot + event only; failed fetch → status failed, no
  transition; transient failure on a scheduled check retries up to 3 attempts, manual checks get 1; sweep picks only
  monitored live placements of approved items; compares latest approved version; findings marked `new`.
- [ ] Commit.

### Task 4: API, demo pages, fetch-url

**Endpoints:** `POST /items/fetch-url` (async; any signed-in role; 422 field `url` with `details.reason`);
`GET /items/{id}/drift` → `ItemDriftOut{placements: [PlacementDriftOut{placement_id, location, url, monitored,
is_live, latest: SnapshotOut | null, demo_page: DemoPageOut | null}]}`; `POST /placements/{id}/drift-checks` → 202
`SnapshotOut`; `GET /demo/partner-pages`, `PUT /demo/partner-pages/{slug}` `{edited}` (lead/admin). Public
`GET /demo-partners/<slug>/` (Django view, no auth). `demo.seed_placement` for L's seed. `edge.tf` path pattern.

- [ ] Tests: API happy paths and 401/403/404/409/422; demo page shows original/edited copy; unknown slug 404;
  query count on `GET /items/{id}/drift`; contract test stub list updated; `make schema`.
- [ ] Commit.

### Task 5: Frontend

- [ ] Restore `FetchFromUrl` (from `2cee562^`), without the `not_implemented` branch; `source_url` back in the
  form; show the backend's reason message; tests (fills copy + title; shows refusal message; loading state).
- [ ] `Placements.tsx` in Details tab: per placement location, URL, run dates, live; monitored → last check line,
  diff (`DiffText`) for modified, findings found on the page (new ones first), "Check now" (polls every 2 s while in
  flight, then invalidates item + history), demo-only "Simulate partner edit" switch for lead/admin; history text
  for the two new events. Tests with MSW.
- [ ] Screenshots of: fetch control idle/loading/error/filled; placement unchanged, checking, modified with diff,
  missing, failed → `docs/plan/reviews/ui/drift/`.
- [ ] Commit.

### Task 6: Review, report, PR

- [ ] One fresh security-minded reviewer → `docs/plan/reviews/drift-monitor.md`; fix; report
  `docs/plan/reports/drift-monitor.md`; PR "Drift monitor and fetch from URL"; CI green.
