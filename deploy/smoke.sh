#!/usr/bin/env bash
# Smoke-test a deployed ClearPath through its public URL (CloudFront), after a
# deploy. Read-only: GETs and one refused POST, no login, no data written.
#
#   deploy/smoke.sh https://dxxxxxxxxxxxxx.cloudfront.net
#
# Run it from the US: the distribution's geo restriction answers 403 to
# everyone else. Runs every check, prints FAIL with the reason (and the start
# of the body) for each one that fails, and exits 1 if any did.
# Needs curl and jq.
set -euo pipefail

base="${1:?usage: smoke.sh <base-url, e.g. https://dxxxx.cloudfront.net>}"
base="${base%/}"
[[ "$base" == https://* ]] || { echo "smoke: base URL must be https://, got ${base}" >&2; exit 2; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
body="$tmp/body"
headers="$tmp/headers"
failures=0

fail() {
  echo "FAIL  $1" >&2
  if [[ -s "$body" ]]; then
    echo "      body: $(head -c 300 "$body" | tr '\n' ' ')" >&2
  fi
  failures=$((failures + 1))
}
pass() { echo "ok    $1"; }

# fetch <path> [curl args...]: status code on stdout; body and headers to files.
fetch() {
  local path="$1"
  shift
  : >"$body"
  : >"$headers"
  curl -sS --max-time 20 -o "$body" -D "$headers" -w '%{http_code}' "$@" "${base}${path}" || echo 000
}

header() { grep -i "^$1:" "$headers" | head -1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//'; }

is_spa_index() { grep -q '<div id="root">' "$body"; }

# 1. API health, with a reachable database (200 even when degraded, so check the body).
status=$(fetch /api/health)
if [[ "$status" == 200 ]] && jq -e '.status == "ok" and .database == true' "$body" >/dev/null 2>&1; then
  pass "/api/health: database reachable"
else
  fail "/api/health: HTTP ${status}, want 200 with {\"status\":\"ok\",\"database\":true}"
fi
# Django's own security headers on an app path: proves CloudFront-Forwarded-Proto
# reaches Django (SECURE_PROXY_SSL_HEADER) so it treats the request as HTTPS.
if [[ -n "$(header strict-transport-security)" ]]; then
  pass "/api/health: Strict-Transport-Security set by Django"
else
  fail "/api/health: no Strict-Transport-Security; Django doesn't see the request as HTTPS"
fi

# 2. SPA index from the frontend bucket, and a deep link rewritten to it.
for path in / /queue; do
  status=$(fetch "$path")
  if [[ "$status" == 200 ]] && is_spa_index; then
    pass "${path}: SPA index.html"
  else
    fail "${path}: HTTP ${status}, want 200 with the SPA's index.html"
  fi
done

# 3. Django admin static files, synced to the frontend bucket under /static/.
status=$(fetch /static/admin/css/base.css)
if [[ "$status" == 200 ]]; then
  pass "/static/admin/css/base.css: admin static files"
else
  fail "/static/admin/css/base.css: HTTP ${status}, want 200 (deploy.yaml syncs collectstatic output)"
fi

# 4. A demo partner page, served by Django (not the SPA): CloudFront must route
# /demo-partners/* to the app, or the drift sweep marks seeded placements missing.
status=$(fetch /demo-partners/lendcompare/)
if [[ "$status" == 200 ]] && ! is_spa_index && grep -qi '<html' "$body"; then
  pass "/demo-partners/lendcompare/: Django demo page"
else
  fail "/demo-partners/lendcompare/: HTTP ${status}, want 200 HTML from Django (an index.html here means the CloudFront behavior is missing)"
fi

# 5. allauth headless config: login by email, public signup closed. Also issues
# the csrftoken cookie the SPA's login needs; production marks it Secure.
status=$(fetch /_allauth/browser/v1/config)
if [[ "$status" == 200 ]] &&
  jq -e '.status == 200 and (.data.account.login_methods | index("email")) and .data.account.is_open_for_signup == false' \
    "$body" >/dev/null 2>&1; then
  pass "/_allauth/browser/v1/config: email login, signup closed"
else
  fail "/_allauth/browser/v1/config: HTTP ${status}, want 200 with login_methods [email] and is_open_for_signup false"
fi
cookie=$(header set-cookie)
if [[ "$cookie" == csrftoken=* && "$cookie" == *[Ss]ecure* ]]; then
  pass "/_allauth/browser/v1/config: csrftoken cookie is Secure"
else
  fail "/_allauth/browser/v1/config: want a Secure csrftoken cookie, got '${cookie:-none}'"
fi

# 6. Signed-out API calls are refused, not served.
status=$(fetch /api/me)
if [[ "$status" == 401 ]]; then
  pass "/api/me signed out: 401"
else
  fail "/api/me signed out: HTTP ${status}, want 401"
fi

# 7. Host header: Django must accept the public host (ALLOWED_HOSTS) and CSRF
# must reject a cross-site POST (Origin not in CSRF_TRUSTED_ORIGINS) with 403.
status=$(fetch /_allauth/browser/v1/auth/login -X POST -H 'Content-Type: application/json' \
  -H 'Origin: https://evil.example' --data '{"email":"nobody@clearpath.demo","password":"x"}')
if [[ "$status" == 403 ]]; then
  pass "cross-origin login POST: 403 (CSRF)"
else
  fail "cross-origin login POST: HTTP ${status}, want 403 from Django's CSRF check"
fi

if ((failures > 0)); then
  echo "smoke: ${failures} check(s) failed against ${base}" >&2
  exit 1
fi
echo "smoke: all checks passed against ${base}"
