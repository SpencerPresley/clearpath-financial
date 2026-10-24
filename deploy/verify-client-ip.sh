#!/usr/bin/env bash
# One-off check after the first deploy: does CloudFront overwrite a
# viewer-supplied CloudFront-Viewer-Address? allauth's rate limits trust that
# header (backend/config/settings/prod.py), and AWS documents the header's
# value but not that a spoofed one is replaced.
#
#   deploy/verify-client-ip.sh https://dxxxxxxxxxxxxx.cloudfront.net
#
# Sends 11 failed logins to allauth's app client (no CSRF), each claiming a
# different viewer address and a different email. allauth allows 10 failed
# logins per IP per minute. If CloudFront replaces the header, all 11 count
# against your real IP and the 11th is refused (too_many_login_attempts): safe.
# If all 11 are plain mismatches, the spoofed values reached Django: remove
# ALLAUTH_TRUSTED_CLIENT_IP_HEADER from prod.py (allauth then uses REMOTE_ADDR,
# which uvicorn derives from X-Forwarded-For via --forwarded-allow-ips).
#
# Side effect: your IP can't log in for about a minute afterwards. The WAF
# login rate rule (50 POSTs / 5 min per IP) isn't reached.
set -euo pipefail

base="${1:?usage: verify-client-ip.sh <https://cloudfront-domain>}"
base="${base%/}"
codes=()
for n in $(seq 1 11); do
  code=$(curl -sS --max-time 20 -X POST "${base}/_allauth/app/v1/auth/login" \
    -H 'Content-Type: application/json' -H "CloudFront-Viewer-Address: 192.0.2.${n}:1" \
    --data "{\"email\":\"spoof-check-${n}@clearpath.invalid\",\"password\":\"not-the-password-${n}\"}" |
    jq -r '.errors[0].code // .status' 2>/dev/null || echo not-json)
  codes+=("$code")
done
echo "responses: ${codes[*]}"
if [[ "${codes[10]}" == too_many_login_attempts ]]; then
  echo "verify-client-ip: OK, CloudFront replaced the spoofed header; rate limits key on the real viewer IP"
else
  echo "verify-client-ip: FAIL, spoofed CloudFront-Viewer-Address values reached Django; see this script's header" >&2
  exit 1
fi
