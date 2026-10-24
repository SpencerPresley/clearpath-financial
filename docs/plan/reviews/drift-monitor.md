# Review: drift monitor and fetch from URL (workstream M, #14)

Branch `wsM/drift` against `origin/main` (6 commits, `18195f9..21af1e9`). Reviewed: `backend/drift/*`,
`reviews/{api,models,rereview}.py` + `0008`, `audit/payloads.py`, `core/domain.py`, settings, `config/urls.py`,
`infra/main/edge.tf`, `frontend/vite.config.ts`, `FetchFromUrl.tsx`, `Placements.tsx`. I checked library behavior
against the installed source in `backend/.venv/lib/python3.13/site-packages/` (httpx2 2.16.0, httpcore2 2.16.0,
django-ninja 1.7.1, anyio 4.15.1). The probes are in
`/private/tmp/claude-501/-Users-spencer-code-promptarmor/51393cec-f963-4ef3-9f0b-5094c8f43a9e/scratchpad/review/`
(`exp1.py` to `exp6.py`). They use an injected resolver and `httpx2.MockTransport`, so none of them touches the
network. `uv run pytest drift -q`: **154 passed**.

I found no SSRF bypass, meaning no way to make the server connect to a denied address in the deployed environment.
The serious problem is a CPU denial of service that sits next to the guard.

---

## Critical

### C1. A page can pick the `punycode` charset and stall a uvicorn worker's event loop for minutes

`backend/drift/fetcher.py:284-292` (`_decode`) is called synchronously at `:326`, inside the coroutine and inside
`asyncio.timeout(deadline)` (`:346`).

**Mechanism (verified).** `_decode` passes whatever charset the page declares to `bytes.decode`. The charset comes
from `response.charset_encoding` (the `Content-Type` parameter) or from `<meta charset=…>`. Python's `punycode`
codec is a text codec, so it passes the `LookupError` fallback, and it is quadratic on a long run of digits:

```
exp3.py   b"-" + b"9"*n  .decode("punycode", errors="replace")
n=50 000   0.31 s
n=100 000  1.26 s
n=200 000  5.01 s
```

End to end through `fetch_page` (`exp4.py`): the resolver returns `93.184.215.14`, and the transport answers
`200 Content-Type: text/html; charset=punycode` with a body of `b"-" + b"9"*300_000` (300 KB). Output:

```
punycode: fetch_page took 12.00s with deadline=1.0; max event-loop stall 12.05s
```

The deadline does nothing here. `asyncio.timeout` can only cancel at an `await`, and the decode is one blocking call.
Extrapolating the quadratic curve to the 2 MB cap gives (2.1M / 200K)² × 5 s ≈ **8 to 9 minutes per request**. I
didn't run 2 MB.

The mechanism and timings are measured. Calling it Critical rather than Important is a judgment about blast
radius: it's not an SSRF, but any account can take the whole web tier down for minutes with two requests.

**Who can trigger it and what it costs.**
- Who: any signed-in user, any role. `POST /api/items/fetch-url` takes any public URL, so the attacker only needs a
  page they host, e.g. `https://attacker.example/x` serving the body above.
- Cost: prod runs `uvicorn --workers=2` (`deploy/compose.prod.yaml`), so two requests stop the whole web tier, health
  checks included. The throttle (`UserRateThrottle("20/m")`, `reviews/api.py`) allows 20 requests a minute.
- The worker path is bounded: `drift.run_check` has `soft_time_limit=60` (`drift/tasks.py:23`). It still burns up to
  60 s of one of the two Celery slots per check.

**Fix.**
- Allowlist the charset. Resolve it with `codecs.lookup(name).name` and accept it only if it is in a fixed set of web
  text encodings: utf-8, utf-16/32 (all variants), ascii, latin-1 / iso8859-*, cp125x, koi8-*, mac-roman, shift_jis,
  euc-jp, iso2022_jp, gb2312/gbk/gb18030, big5, euc-kr. Anything else decodes as UTF-8 with replacement.
  - That rejects `punycode`, `idna`, `utf-7`, `unicode_escape`, `raw_unicode_escape` and `undefined`.
- Add a test with `charset=punycode` and a 200 KB digit body that asserts it finishes quickly.
- Running `_decode` in `asyncio.to_thread` is **not** a fix on its own. Threads can't be cancelled, the codec is pure
  Python and holds the GIL, and the executor thread stays busy for minutes.

---

## Important

### I1. `charset=idna` (or `undefined`) raises a raw `UnicodeError` out of `fetch_page`, so fetch-url returns a 500

Same spot, `fetcher.py:289-292`. Only `LookupError` is caught there.

**Verified.**
- `exp2.py`: `b"<p>hi</p>".decode("idna", errors="replace")` raises `UnicodeError: Unsupported error handling:
  replace`, and the `undefined` codec raises `UnicodeError: undefined encoding`.
- `exp4.py`: `fetch_page` with `Content-Type: text/html; charset=idna` lets the error out as
  `UnicodeError Unsupported error handling: replace`. `<meta charset="idna">` does the same.

**Effect.**
- `intake.fetch_copy` (`drift/intake.py:27-30`) catches only `FetchError`, so the user gets an unhandled 500 instead of
  the typed 422 the module promises ("every refusal and failure is a 422 on `url`"). This breaks invariant D: typed
  errors are supposed to be mapped once.
- The drift task catches it generically and records `error_code="error"` with no useful reason.

**Fix.** The C1 allowlist removes the cause. As a safety net, also catch `(LookupError, UnicodeError)` in `_decode`
and fall back to UTF-8 with replacement.

### I2. `details.reason` tells callers whether a name exists on the VPC resolver

The two branches are in `fetcher.py:218-225`; `intake.py:30` passes the code through to the client.

**Verified (`exp5.py`, with a resolver standing in for the VPC's private answers):**

```
http://payments-admin.internal/  -> reason=address_not_allowed
http://nothing-here.internal/    -> reason=dns_failed
```

**Mechanism.** The host is resolved before the address check, and the two outcomes come back as different reason
codes. Any marketer can therefore use 20 requests a minute to enumerate names that resolve only inside the VPC, and
learn that they map to private ranges. No connection is ever made.
- What's exposed today: `infra/main/network.tf` enables `enable_dns_hostnames`, so the leak covers EC2
  `ip-10-…ec2.internal` names and any RDS or ElastiCache endpoint.
- It gets worse the day someone adds a Route 53 private hosted zone. There is none today; I grepped `infra/` for
  `aws_route53_zone`.

This is judgment: it's an information leak, not an access path. The bar here is a security company's, and the fix is
one line.

**Fix.** For host names (not IP literals), return the same public reason and message for "didn't resolve" and
"resolved to a denied network", e.g. both as `address_not_allowed` with "That address can't be fetched." Keep the
distinction in server logs and in the drift snapshot's `error_code`. Reviewers see that, and placement URLs come from
owners or leads anyway.

---

## Minor

- **M1. Some IPv6 forms are missing from the denied list** (`fetcher.py:66-80, 155-168`). Verified with `exp1.py`;
  these all return `denied=False`:
  - `64:ff9b:1::a9fe:a9fe`: RFC 8215 local-use NAT64 `64:ff9b:1::/48`, i.e. the metadata address behind a local
    NAT64.
  - `::a9fe:a9fe` / `::127.0.0.1`: IPv4-compatible `::/96`.
  - `::ffff:0:7f00:1`: IPv4-translated `::ffff:0:0/96`.
  - `3fff::1` (`3fff::/20`, documentation) and `5f00::1` (`5f00::/16`, SRv6 SIDs).

  Today none of these can be reached from prod: the VPC has no IPv6 (`grep -rn ipv6 infra` finds only CloudFront's
  `is_ipv6_enabled = false`), and Linux doesn't route `::/96` to IPv4 without `sit`. That is defense in depth only,
  and a dual-stack dev laptop or a future IPv6 VPC changes it.

  Fix: unwrap `64:ff9b:1::/48` the way `64:ff9b::/96` is unwrapped, and add `::/96`, `::ffff:0:0/96`, `3fff::/20`
  and `5f00::/16` to `_DENIED_V6`. `IPv6Address.is_reserved` (which covers `::/8`) would also do as a backstop
  without giving up the explicit list.
- **M2. The dev allowlist exempts whole origins, not the demo path** (`config/settings/dev.py:15`; `fetcher.py:208,
  224`).
  - In dev, `http://localhost:8000/<anything>` and `http://localhost:5173/<anything>` skip the address rule. That
    includes whatever Vite serves as `text/html` or `text/plain`, and the Django dev server's public pages.
  - This is local-only. Prod and test import `base` (`prod.py:1`, `test.py:1`; `deploy/compose.prod.yaml:18` sets
    `DJANGO_SETTINGS_MODULE=config.settings.prod` for web, worker and beat), and two tests pin the empty list
    (`test_fetcher.py:562-570`).
  - However, `config/asgi.py:5` and `config/celery.py:5` default to `config.settings.dev` when the variable is unset,
    so one missing env var turns the exemption on in a deployed box.

  Fix: match the allowlist on origin **and** a path prefix (`/demo-partners/`). Also make the fetcher ignore the list
  unless `settings.DEBUG` is set, or assert that it's empty in `prod.py`.
- **M3. "Check now" has no throttle** (`drift/api.py:22-32`). The in-flight dedup stops double-clicks, but a finished
  check can be requested again straight away.
  - Each check stores up to 100 000 chars in `Snapshot.text`. An owner can point N placements at slow-drip URLs and
    hold the two shared Celery slots for about 15 s each, in the same queue as the LLM checks and terms fan-out.
  - Fix: a per-user throttle, and/or a dedicated `drift` queue.
- **M4. The reconciler measures "lost" from `requested_at`, not from when the check was last released**
  (`services.py:381-383, 394-399`).
  - If the sweep backlog exceeds 10 minutes, every pending snapshot is re-enqueued every 5 minutes. `claim` makes the
    extra copies no-ops, but they're noise.
  - A snapshot that is legitimately queued for more than an hour gets failed as `stuck`.
  - Fix: key on `max(requested_at, started_at)`, or store a `queued_at` that `release` refreshes.
- **M4b. The TLS hostname is safe across redirects only by accident of the close path (latent).**
  - One `AsyncClient`/pool serves every hop (`fetcher.py:298-303`).
  - httpcore2 decides whether to reuse a connection with `can_handle_request(origin)`, i.e.
    `origin == self._origin` (`connection_pool.py:343-344`, `connection.py:151-152`). The origin is
    `(scheme, pinned IP, port)`; `sni_hostname` isn't in the key.
  - Reuse doesn't happen today. The redirect response's body is never read, and `_response_closed`
    (`httpcore2/_async/http11.py:219-229`) returns a connection to the pool only when h11's `their_state is DONE`.
    Otherwise it closes the connection.
  - `exp6.py` confirms this. A mock backend serves `302 Location: http://b.example/` and then a `200` on connection 1,
    and both hosts resolve to the same IP. Both with `Content-Length: 0` and with a body, the fetch opens **2
    connections**, so hop 2 does its own handshake and certificate check.
  - The risk is a future change that drains redirect bodies (e.g. `await response.aread()` before `aclose`). That
    would make `https://a.example` → `302 https://b.example` on a shared IP send `Host: b.example` over a session
    verified for `a.example`.
  - Fix: build the transport with `limits=httpx2.Limits(max_keepalive_connections=0)` (or one client per hop), so
    this no longer depends on the close path. Turn `exp6.py` into a test.
- **M4c. Slow DNS lookups and page parsing share one thread pool.** `loop.getaddrinfo` (`fetcher.py:151`) runs in
  the loop's default executor, and so does `asyncio.to_thread(visible_text, …)` (`intake.py:32`). Host names whose
  authoritative DNS hangs can tie up those threads, and the deadline doesn't free them. Intake extraction then waits
  behind them. Low impact (the throttle applies), but a small dedicated executor for DNS would separate the two.
- **M5. TLS certificate failures are reported as `connect_failed` and retried as transient.** `ssl.SSLError` maps to
  `ConnectError` (`httpcore2/_backends/anyio.py:68`), and `fetcher.py:245-246` then just tries the next address. A
  partner with an expired certificate shows "The site didn't accept a connection" and uses up 3 scheduled attempts.
  Fix: detect `ssl.SSLCertVerificationError` in the exception chain and map it to a non-transient code such as
  `tls_failed`.
- **M6. A failed `DRIFT_CHECKED` event drops `http_status`.** The snapshot stores it (`services.py:309`), but
  `DriftCheckedPayload` has no field for it (`audit/payloads.py`; the failure event is built at `services.py:316-321`).
  The history event for a 404 or 503 can't say which it was.
- **M7. `asyncio.to_thread(visible_text, …)` (`intake.py:32`) only reduces event-loop blocking; it doesn't remove
  it.** bs4 with `html.parser` is pure Python and holds the GIL, so a 2 MB page still slows the loop down. That's an
  acceptable trade-off; the comment just shouldn't say the loop is free.
- **M8. Judgment: drift detection is easy for a partner to evade.**
  - The User-Agent openly identifies the bot (`ClearPathComplianceBot/1.0`, `fetcher.py:40`), so a partner can serve
    the approved copy to the bot and something else to people.
  - Copy hidden by a stylesheet class (`.x{display:none}`) still counts as visible (`extract.py` only checks inline
    styles), and `compare` returns `unchanged` whenever the approved copy appears anywhere in the page text
    (`compare.py:139-140`).
  - Honest identification is a defensible choice, but it's a product decision, so it should be in `decisions.md`
    rather than happen implicitly.
  - At minimum, findings flagged `new` on an `unchanged` page should be visible in the UI. They are today, in
    `Placements.tsx`.

---

## Verified-OK

**SSRF guard**
- **The resolved IP is pinned, and TLS still checks the hostname.**
  - `fetcher.py:240-241` puts the checked IP in the URL host.
  - `httpcore2/_async/connection.py:108-117` connects to `self._origin.host` (that IP), and `:136` uses
    `sni_hostname` as `server_hostname`.
  - `anyio.connect_tcp` on an IP literal doesn't do another DNS lookup (`anyio/_core/_sockets.py:221-230`: when
    `ip_address(remote_host)` parses, `target_addrs` is built directly and `getaddrinfo` is skipped). A rebinding
    attack has no second lookup to win.
  - IPv6 answers get brackets: `exp1.py` shows `copy_with(host="2606:4700::1111")` producing
    `https://[2606:4700::1111]/path?q=1` with `Host: partner.example`.
- **No proxy or env path.** `httpx2/_client.py:1495` reads `allow_env_proxies = trust_env and transport is None`, and
  the transport is always passed explicitly with `trust_env=False`. No `.netrc`, no `*_PROXY` variables.
- **Numeric host forms are fine.** httpx2 treats `127.1`, `0x7f.0.0.1`, `2130706433` and `017700000001` as host names
  rather than IP literals (`exp1.py`). The system resolver turns each into `['127.0.0.1']` (`exp5.py`), and that
  answer is what gets checked and connected to, so they are denied.
  - `0` resolves to `['0.0.0.0']`, which is denied.
  - `localhost` resolves to `['::1','127.0.0.1']`; both are checked and both are denied.
- **Userinfo and parser tricks are refused, or harmless because the connection uses the checked IP.**
  `http://evil.com\@127.0.0.1/`, `http://evil.com@127.0.0.1` and `http://localhost:8000@evil.com/` are all refused
  as credentials. `http://127.0.0.1#@evil.com/` has host `127.0.0.1`, so it's denied. `\`, `%`-encoded and IDN
  look-alike hosts either fail IDNA (`ⓛocalhost` gives `invalid_url`) or go to the resolver.
- **Unusual ports are fine.** `http://host:0/` checks as port 80, and httpcore's `Origin` uses `port or default_port`
  (`httpcore2/_models.py:286`), so the connection also goes to 80.
- **Mapped, NAT64 `/96`, 6to4 and Teredo addresses are unwrapped and denied correctly**: `::ffff:169.254.169.254`,
  `64:ff9b::a9fe:a9fe`, `2002:a9fe:a9fe::`, `2002:c0a8:101::` and `2001:0:…` all come back denied. So do
  `fd00:ec2::254` (the AWS IPv6 IMDS address) and scoped `fe80::1%eth0` (`exp1.py`).
- **Refusals don't connect first.** Scheme, port, userinfo and IP-literal refusals all happen in
  `_target`/`_addresses`, before `_send`. Only host names cause a DNS lookup. `test_fetch_url_goes_through_the_real_guard`
  hits `169.254.169.254` through the real stack and gets a 422 without connecting.
- **Redirects are re-validated.** `follow_redirects=False`, and each hop goes back through
  `_target`/`_addresses`/pinning. That covers a redirect to IMDS, to a private name, or to `ftp:`, and allows at most
  5 hops (tests `:267-336`).
- **Cookies and credentials don't leak.** The cookie jar is cleared before every send, no `Authorization` header is
  ever set, and the `Accept-Encoding: identity` header overrides httpx2's default.
- **Compression is handled.**
  - Any `Content-Encoding` other than `identity` is refused. Several headers are joined (`identity, gzip`) and
    refused too.
  - Several `Content-Type` headers are joined, so the media type no longer matches and the response is refused.
- **Size and time limits hold.**
  - The 2 MB cap counts bytes read; at most one 64 KB chunk past the cap is read before the check fires.
  - The total deadline covers DNS, connect and slow-drip reads (`test_total_deadline`); the C1 decode is the only
    thing that escapes it.
- **The cloud metadata service is protected anyway.** EC2 requires IMDSv2 (`infra/main/app.tf:59-64`, `http_tokens =
  "required"`), so even an IMDS bypass would get no credentials from a plain GET. There are no VPC endpoints or
  `aws:SourceVpc`-style policies in `infra/`.

**Authorization and abuse**
- **fetch-url** is any signed-in role (`django_auth`, CSRF on POST), with input validated as `^https?://` and at most
  2000 chars.
  - In ninja 1.7.1 the async auth runs the sync `SessionAuth` through `sync_to_async` (`ninja/operation.py:570`), so
    the DB query stays off the event loop.
  - The throttle runs after auth, on the already-resolved `request.user` (`throttling.py:244`). Its Redis get/set is
    a brief synchronous call on the loop, which is acceptable.
  - The 21st request returns 429 (`test_fetch_url_is_rate_limited_per_user`).
- **Check now** is limited to the owner or a reviewer, lead or admin (`services.py:97-99`). The demo switch is lead or
  admin only (`demo.py:145`).
- **`GET /items/{id}/drift` has no viewer check**, which matches `get_item_detail` (`reviews/records.py:311`): every
  signed-in user can read every item.
- **Demo pages reflect nothing from the request.**
  - The template only renders `demo.PAGES` constants plus the date and reader count, all autoescaped. The page is
    `require_safe` and `never_cache`.
  - `XFrameOptionsMiddleware` is installed (`base.py:114`) and prod sets `X_FRAME_OPTIONS = "DENY"`.
  - CloudFront uses `caching_disabled` for every app path, including `/demo-partners/*` (`edge.tf:154-167`).
  - The pages are same-origin with the SPA but run no script, so the session cookie being sent to them exposes
    nothing.
- **Frontend.** `placement.url` passes `URLValidator(schemes=["http","https"])` (`reviews/placements.py:83`) before
  it becomes `<a href target=_blank rel="noopener noreferrer">` (`Placements.tsx:188`). There is no
  `dangerouslySetInnerHTML`, and server messages render as text.

**Drift semantics and invariants**
- **The latest approved version is what's compared.** `_latest_approved_version` runs again under the item lock, and
  the analysis is redone if the item was re-approved during the fetch (`services.py:245-252`).
- **Reopen happens only when** the result is modified or missing, the item is `approved` and not legacy, and the
  placement is live (`services.py:286, 296-299`).
- **Locks are taken in the same order everywhere**: item, then placement or snapshot, then (inside `reopen_item`) the
  item again in the same transaction, then the assignment advisory lock. That matches `reviews.assignment`.
  - `claim` locks only the snapshot and takes nothing else, so there is no lock cycle.
  - Each transaction touches one item.
- **The task is idempotent.**
  - `claim` acts only on `pending`, and `complete`/`fail` act only on `running` with a matching `attempts`.
  - Duplicate deliveries do nothing.
  - Retries stay within `MAX_SCHEDULED_ATTEMPTS` and Celery's `max_retries=2`.
  - A partial unique index allows one in-flight check per placement, and check constraints enforce "result iff
    succeeded" and "failed has a code".
- **Events go in the same transaction as the state they describe**: `DRIFT_CHECK_REQUESTED` with the pending snapshot,
  and `DRIFT_CHECKED` plus `ITEM_REOPENED` (carrying `snapshot_id`) with the result.
  - The enqueue runs `on_commit`.
  - Snapshot rows are written only by `drift.services`.
- **Migration.**
  - `makemigrations --check --dry-run` reports "No changes detected".
  - `0008` adds the three constraints exactly as they are in `models.py`, then drops `fetched_at`, and converts
    `diff` from text to JSON.
  - The cast and the new constraints can't fail on existing data: nothing on `origin/main` ever wrote a `Snapshot`
    (`git grep Snapshot origin/main -- backend` outside migrations finds only the model), so the table is empty.
- **No deadlock on the single sync thread.** fetch-url awaits on the event loop, and the demo view it may fetch runs on
  the sync thread, which the async view never holds.

---

## Resolutions (implementer, after the review)

| Finding | Resolution | Test |
|---|---|---|
| C1 punycode decode stall | Fixed. `_codec` resolves the declared charset with `codecs.lookup(...).name` and accepts only a fixed set of web text encodings; anything else decodes as UTF-8 with replacement. | `test_non_web_charsets_decode_as_utf8[punycode,idna,undefined,utf-7,unicode_escape,rot13]` (300 KB body under 2 s), `test_meta_punycode_charset_is_ignored` |
| (found while fixing C1) quadratic extraction | Fixed. `visible_text` mutated the tree per block (`insert_before`/`insert_after` walk `_last_descendant`, O(depth)), so `"<div>" * 80_000` (400 KB) took **73 s**. Rewritten as one iterative, non-mutating pass: the same input now takes 0.37 s. | `test_deep_nesting_is_linear_not_quadratic`, `test_comments_doctype_and_cdata` |
| I1 `idna`/`undefined` → 500 | Fixed by the allowlist; `_decode` also catches `(LookupError, UnicodeError)`. | as C1 |
| I2 name enumeration | Fixed. A host *name* that doesn't resolve and one that resolves to a denied address both raise `host_not_reachable` with one message; `FetchError.detail` keeps the cause for logs (the task log line prints it). The snapshot stores the public code too: owners can trigger Check now and read the result, so storing the distinction there would reopen the oracle. IP literals still say `address_not_allowed` (nothing to enumerate). | `test_unresolvable_and_private_names_look_the_same_to_the_caller` |
| I3 pooled TLS per IP | Fixed. A fresh `AsyncClient` (and pool) per hop. | `test_each_redirect_hop_gets_a_fresh_connection_pool` |
| M1 IPv6 gaps | Fixed. Added `::/96`, `::ffff:0:0/96`, `::ffff:0:0:0/96`, `64:ff9b:1::/48`, `3fff::/20`, `5f00::/16`, plus `is_reserved` as a backstop. | `test_denied_addresses` (6 new cases) |
| M2 dev allowlist scope | Fixed. Exempt only for an allowlisted origin **and** a `/demo-partners/` path, and the settings list is ignored unless `DEBUG`. | `test_allowlist_covers_only_the_demo_pages`, `test_settings_allowlist_is_ignored_outside_debug` |
| M3 Check now unthrottled | Fixed. `drift/throttles.py`: Check now 10/min per user, fetch-url 20/min, each with its own scope (ninja keys history by scope + user, so two plain `UserRateThrottle`s would share one budget). A dedicated Celery queue is left for the deploy wave. | `test_check_now_is_rate_limited_on_its_own_budget` |
| M4 reconciler timing | Deferred. Duplicate enqueues are no-ops (`claim` only takes `pending`); a queue over an hour deep is an outage the reconciler can't fix. Noted in the report. | — |
| M5 TLS as connect_failed | Fixed. An `ssl.SSLError` in the chain is `tls_failed`, not transient, and stops trying other addresses. | `test_tls_failure_is_its_own_permanent_error` |
| M6 http_status missing on the event | Fixed. `DriftCheckedPayload.http_status`. | covered by the service failure tests |
| M7 to_thread comment | Fixed (comment now says it shares the loop's GIL). | — |
| M8 evasion | Product decision; listed in the report's decisions needed. | — |
