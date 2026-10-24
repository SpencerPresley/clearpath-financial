#!/usr/bin/env bash
# Runs on the app server as root via SSM Run Command (see
# .github/workflows/deploy.yaml, which ships this directory alongside it).
#
#   deploy.sh <account>.dkr.ecr.<region>.amazonaws.com/clearpath/backend:<git-sha>
set -euo pipefail

image="${1:?usage: deploy.sh <backend-image-ref>}"
# Run Command doesn't always set HOME; docker login stores credentials under it.
export HOME="${HOME:-/root}"
cd /srv/clearpath

./render-env.sh "$image"

registry="${image%%/*}"
region=$(cut -d. -f4 <<<"$registry")
aws ecr get-login-password --region "$region" |
  docker login --username AWS --password-stdin "$registry"

compose=(docker compose -f compose.prod.yaml)

"${compose[@]}" pull --quiet

# Migrate before swapping containers: until `up` replaces them, the old code
# serves against the new schema, so migrations must stay backward-compatible
# (expand, deploy, then contract). The reverse order would run new code
# against the old schema until migrate finished.
"${compose[@]}" run --rm --no-deps web python manage.py migrate --noinput

# The demo's seeded data (docs/demo.md): a no-op once any items exist, so only
# the first deploy onto an empty database seeds. Here rather than in the web
# container's command: a failure stops the deploy while the old containers
# still serve, and the first seed (~10 s locally, longer against RDS) doesn't
# eat into the web healthcheck's window. With deps (unlike migrate): the seed
# sets the demo partner pages' state in Redis, which on a first deploy isn't
# running until this starts it.
"${compose[@]}" run --rm web python manage.py seed_demo

# --wait blocks until healthchecks pass and exits non-zero if they don't,
# which fails the SSM command and therefore the workflow.
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout 180

# /api/health answers 200 even when degraded; require a reachable database.
curl -fsS http://localhost:8000/api/health | jq -e '.database == true' >/dev/null
echo "deploy: ${image} is up and healthy"

# Old images stay in ECR (last 20) for rollback; the disk only needs recent ones.
docker image prune -af --filter "until=72h" >/dev/null
