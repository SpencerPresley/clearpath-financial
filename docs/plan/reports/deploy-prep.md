# Report: deploy-prep

Branch `deploy/prod-readiness`, rebased on main after #39 (demo seed) merged. Nothing applied or deployed;
`terraform plan` was read-only (`-lock=false`).

## What changed

| # | Area | Change | Files |
|---|---|---|---|
| 1 | AI key required | One list of production requirements, enforced in three places, never at settings import. | `backend/core/deploy_checks.py`, `config/asgi.py`, `config/celery.py`, `deploy/deploy.sh` |
| 2 | DB connections | `CONN_MAX_AGE = 0` plus a psycopg pool `{"min_size": 1, "max_size": 8, "timeout": 10}` in base (dev, test and prod). | `config/settings/base.py` |
| 3 | File storage | S3Storage on `DOCUMENTS_BUCKET`, `file_overwrite=False`, no ACL. Downloads still stream through the existing endpoints. The IAM role loses `DeleteObject` and gains `AbortMultipartUpload`. | `config/settings/prod.py`, `infra/main/app.tf`, `storage.tf` |
| 4 | Hosts / URLs | Terraform already derives all four values. The deploy check now enforces them (explicit hosts, https `FRONTEND_BASE_URL` on an allowed host, https CSRF origins), and render-env.sh requires them to be present. | `core/deploy_checks.py`, `deploy/render-env.sh` |
| 5 | Client IP | `ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "CloudFront-Viewer-Address"` in prod. | `config/settings/prod.py` |
| 6 | Processes | Per-service log rotation; a worker healthcheck (`inspect ping`); stop grace periods; one beat; the deploy check runs before migrate. | `deploy/compose.prod.yaml`, `deploy/deploy.sh` |
| 7 | Smoke | `deploy/smoke.sh <base-url>` runs 10 checks. `deploy/verify-client-ip.sh` is a one-off spoofing test. | `deploy/` |
| + | **Public signup was open** | allauth's default adapter left `/_allauth/*/v1/auth/signup` open. A stranger could create a signed-in, role-less account. Fixed by an adapter that closes signup. | `accounts/adapter.py`, `config/settings/base.py` |

### 1. AI key required in prod: why this shape

The constraints pull in different directions:
- CI's `build-backend` job runs `collectstatic` on `config.settings.prod` with only `DJANGO_SECRET_KEY`
  and `POSTGRES_PASSWORD`.
- `config/__init__.py` imports `config.celery` into every management command.
- Django's model checks open a database connection. I observed this: `check --deploy` without a reachable
  Postgres dies in `check_all_models` with `OperationalError`.

So:
- A **settings-import check is out**: it would break collectstatic.
- A **module-level guard in `config/celery.py` is out** for the same reason.
- A **`check --deploy` in CI is out**: CI has no database.

What I built: `core/deploy_checks.py` holds `production_config_problems()`, gated on
`PRODUCTION_CONFIG_REQUIRED`, which is True only in prod.py. It checks the following:

| ID | What it requires |
|---|---|
| `clearpath.E001` | The key is non-empty, isn't Terraform's `placeholder-set-out-of-band` and starts with `sk-ant-`. |
| `clearpath.E002` | Default storage is S3Storage with a bucket. |
| `clearpath.E003` | Explicit `ALLOWED_HOSTS`. |
| `clearpath.E004` | `FRONTEND_BASE_URL` is https and its host is in `ALLOWED_HOSTS`. |
| `clearpath.E005` | The CSRF origins are https. |

The placeholder check matters. Terraform always writes the parameter, so render-env.sh's presence check
can't tell the placeholder from a real key.

It's enforced in three places:
- **deploy.sh**: `manage.py check --deploy --fail-level WARNING`, as a one-off container after `pull` and
  before `migrate`. If it fails, the deploy stops while the old release keeps serving. The check is
  registered with `@register(Tags.security, deploy=True)`, which Django documents as running only under
  `check --deploy` (topics/checks), so plain `check` in CI is unaffected.
  - `--fail-level WARNING` means Django's own deploy warnings also block a deploy. Two are silenced in
    prod.py with reasons:
    - W008 `SECURE_SSL_REDIRECT`: CloudFront enforces HTTPS, and the localhost healthchecks would break
      under a redirect.
    - W021 HSTS preload: preloading isn't ours to do for `cloudfront.net`, and the custom domain's parent
      shouldn't be preloaded by this app.
- **ASGI**: `require_production_config()` runs in `config/asgi.py` after `get_asgi_application()`.
  - Observed: uvicorn `--workers 2` keeps respawning children, each of which raises
    `ImproperlyConfigured`. The container never serves, the healthcheck fails, and `up --wait` fails.
    That's slow (180 s) but loud. The deploy.sh pre-check normally catches it first.
- **Celery worker and beat**: a `worker_init` / `beat_init` receiver raises `SystemExit(1)`.
  - It can't simply raise the error. Celery's `Signal.send` catches `Exception` from receivers and only
    logs it (`celery/utils/dispatch/signal.py:281-285`), so raising `ImproperlyConfigured` would let the
    worker start anyway.
  - Observed: worker and beat both exit 1 with the E00x list. With good config the worker starts and
    answers `inspect ping`.

Alternatives rejected:
- A shell wrapper (`check && exec celery`) in the compose commands. It costs an extra Django boot per
  container start and doesn't cover a manual `docker compose up`.
- Making `Env.anthropic_api_key` required in prod. That breaks collectstatic.

### 2. DB connections under ASGI

Django 6.1 docs, verified via ctx7:
- topics/async: "Persistent database connections, set via the `CONN_MAX_AGE` setting, should also be
  disabled in async mode. Instead, use your database backend's built-in connection pooling."
- ref/databases: "The `CONN_MAX_AGE` setting must be `0` when connection pooling is enabled." Also
  "Unless a `check` callback is provided in the pool options, `CONN_HEALTH_CHECKS` determines whether
  connections are checked when retrieved from the pool."

Main had `CONN_MAX_AGE = 60` under uvicorn, in dev as well. I put the pool in base so dev and CI use it
too. The full suite passes with it: 1829 passed.

Numbers, from installed sources:
- **psycopg_pool `ConnectionPool` defaults** are `min_size=4` and `max_size=None`, which means a fixed 4
  (`psycopg_pool/pool.py:49-50`).
- **Celery 5.6.3's Django fixup** calls `conn.close_pool()` after every task under prefork
  (`celery/fixups/django.py:219-234`). Each task therefore reopens the pool and fills it to `min_size`.
  With the default 4, that's 3 wasted connections per task. Hence `min_size=1`.
- **`timeout=10`**: a saturated pool raises after 10 s instead of queueing toward CloudFront's 60 s origin
  timeout.

**Sizing against db.t4g.micro.** RDS PG17 default `max_connections = LEAST({DBInstanceClassMemory/9531392},
5000)`, from `aws rds describe-engine-default-parameters --db-parameter-group-family postgres17`. 1 GiB
gives at most 112, minus OS reserve (expect roughly 80–110; read it after apply, see the runbook).
`reserved_connections=2` and `superuser_reserved_connections=3` come off the top.

| Consumer | Peak connections |
|---|---|
| web: 2 uvicorn workers × pool max 8 | 16 |
| worker: 2 prefork children, one task each, pool closed per task | 2 |
| beat (file scheduler, no ORM) | 0 |
| assistant: AsyncPostgresSaver opens its own unpooled connection per run or state read | 1 per concurrent assistant run |
| deploy one-offs (check, migrate, seed_demo; sequential) | 1 |
| **Total at demo load** | **~20–25** |

Headroom is about 4×. One caveat: a live assistant SSE stream holds its request's pooled connection until
the stream ends, so 8 concurrent streams in one uvicorn worker would starve that worker's pool. That's
fine for a demo. Raise `max_size` if it ever matters; the budget allows it.

### 3. File storage on S3

django-storages 1.14.6, checked in ctx7 docs and `storages/backends/s3.py`.

- `file_overwrite` defaults to **True** (`s3.py:410`). With True, `get_available_name` returns the same
  name (`s3.py:702-707`).
  - Attachments use `upload_to="attachments/%Y/%m/"` plus the original filename. A second `memo.pdf` in
    the same month would silently replace the first's bytes, and the first Attachment row's sha256 would
    stop matching.
  - `file_overwrite=False` restores FileSystemStorage's suffixing. There's a test for it.
- `default_acl` is left unset. The bucket is BucketOwnerEnforced, so objects are private by default.
- `max_memory_size = 5 MB`. `S3File` buffers the whole object in a `SpooledTemporaryFile(max_size=0)` by
  default, which never spools (`s3.py:168-171`), so a large export would sit in RAM. Above 5 MB it now
  spools to `/tmp`.
- `staticfiles` stays on local `StaticFilesStorage`. deploy.yaml copies `/app/staticfiles` into the
  frontend bucket.

**Downloads stream, not presign.** My call:
- The existing endpoints (`reviews/api.py` `download_attachment`, `exports/api.py` `download_export`)
  check permission, then `FileResponse(file.open("rb"))`. That works unchanged on S3.
- A presigned URL would be a bearer link. It stays valid after the user is deactivated or loses access,
  and it leaks through history, logs and forwards.
- It would also put `s3.amazonaws.com` in the browser, outside WAF and the geo restriction. The SPA's
  `<a download>` and `<img src=download_url>` would need CORS or CSP thought.
- Cost of streaming: bytes pass EC2 and the NAT ($0.045/GB). That's negligible here. CloudFront's 60 s
  read timeout is per packet, not per response.
- I updated `docs/decisions.md` (Hosting) and the storage.tf comment, which both said "presigned".

**IAM (least privilege)**:
- The role already had ListBucket, GetObject, PutObject and DeleteObject.
- **Removed `DeleteObject`.** Nothing deletes a stored file: attachments are immutable, and Reset demo
  TRUNCATEs rows only.
- **Added `s3:AbortMultipartUpload`.** boto3 goes multipart above 8 MB. PutObject covers Create, UploadPart
  and Complete, but not Abort. The 7-day lifecycle rule stays as a backstop.
- ListBucket stays, so `HeadObject` on a missing key returns 404, not 403. `file_overwrite=False` probes
  with `exists()` (`s3.py:582-594`).
- No KMS, since the bucket is SSE-S3.

**All four file paths covered**: attachments, imports, view exports and evidence packs.
- `exports/tests/test_s3_storage.py` runs them over HTTP on moto with prod.py's exact S3 options.
- Each test checks that bytes land in the bucket, that objects have owner-only grants, that the download
  endpoint returns the same bytes, that unauthenticated requests get 401, and that a duplicate name gets
  a new key.
- The evidence pack test reads its evidence from S3 and writes the zip back to S3.

### 4. URLs and hosts

`infra/main/config.tf` already writes `DJANGO_ALLOWED_HOSTS` (CloudFront domain, the custom domain when
attached, and `localhost` for the healthcheck), `DJANGO_CSRF_TRUSTED_ORIGINS` (`https://<host>`) and
`FRONTEND_BASE_URL`. render-env.sh emits every direct child of the prefix.

What was missing was enforcement: E003, E004 and E005, plus render-env.sh refusing if any of the four
(or `DOCUMENTS_BUCKET` or `ANTHROPIC_API_KEY`) is absent. Secure cookies were already set in prod.py.

The local e2e run (below) showed the following on prod settings:
- the csrftoken cookie is `Secure`;
- HSTS is present when `CloudFront-Forwarded-Proto: https` is sent;
- a cross-origin POST gets 403.

### 5. Client IP for rate limits

allauth 65.20.1:
- **Docs** (ctx7): `ALLAUTH_TRUSTED_CLIENT_IP_HEADER`: "If your service is running behind a trusted proxy
  that sets a custom header containing the client IP address, specify that header name here."
- **Source** (`allauth/core/internal/httpkit.py:213-221`): when the header is set, `get_client_ip` reads
  only that header. It never falls back to REMOTE_ADDR. The value goes through `clean_client_ip`, which
  strips the port.
  - `203.0.113.7:46532` → `203.0.113.7` (run).
  - Unbracketed IPv6 `2001:db8::1:46532` → `None`, which means 403. IPv6 is off on the distribution
    (`is_ipv6_enabled = false`); re-check before enabling it.
- **The header reaches Django.** `Managed-AllViewerAndCloudFrontHeaders-2022-06` includes
  `CloudFront-Viewer-Address` (`aws cloudfront list-origin-request-policies --type managed`).

Tests (`accounts/tests/test_client_ip.py`):
- The adapter returns the header's IP and ignores X-Forwarded-For and REMOTE_ADDR.
- A request without the header gets PermissionDenied on rate-limited flows, but `/api/health` and
  `/_allauth/browser/v1/config` still answer 200 without it, so the healthchecks are safe.
- 11 failed logins from one viewer address hit `too_many_login_attempts` even with X-Forwarded-For
  rotating, and a different viewer address is unaffected.

**Unverified: does CloudFront overwrite a viewer-supplied `CloudFront-Viewer-Address`?** The AWS page
documents the value, not that a spoofed one is replaced. `deploy/verify-client-ip.sh` settles it after the
first deploy. The fallback, if it fails, is to delete the setting: allauth then uses REMOTE_ADDR, which
uvicorn derives from X-Forwarded-For via `--forwarded-allow-ips`. That path is documented safe, since
CloudFront appends the viewer IP per the custom-origin doc.

**Logging**:
- uvicorn's access log shows the X-Forwarded-For-derived viewer IP.
- Django's own log lines carry no client IP.
- No app code reads REMOTE_ADDR (grep).

### 6. Processes

`deploy/compose.prod.yaml`:
- **web**: uvicorn with `--proxy-headers` and 2 workers, as before, plus a 30 s `stop_grace_period`.
- **worker**:
  - `--hostname=worker@%h`, with healthcheck `celery -A config inspect ping --destination
    worker@$HOSTNAME`. Observed locally: exit 0 when consuming, exit 69 when no node replies.
  - `start_period` 60 s with `start_interval` 5 s, so `up --wait` proves the worker started and is
    consuming.
  - `stop_grace_period` 90 s. Tasks are acks_late, so a cut-off task is redelivered.
- **beat**: exactly one service, no healthcheck (beat has no ping), restart policy only.
- **Logging**: json-file 20m×5, set explicitly per service. user_data's daemon.json applies only at first
  boot.
- **No awslogs**: the instance role has no `logs:*` permissions and Terraform creates no log group. Adding
  them is an infra and cost decision, not done.

**Runtime dependencies**:
- Redis: the compose service at `redis://redis:6379/0`, used for the cache (allauth counters, demo-page
  state) and the broker.
- Postgres extensions: `core/migrations/0001` creates `btree_gist` and `pg_trgm`, and nothing else creates
  extensions (grep).
  - AWS's "Extension versions for RDS for PostgreSQL" table lists btree_gist 1.7 and pg_trgm 1.6 for every
    PG17 minor, including 17.9, the current default (`aws rds describe-db-engine-versions --default-only`
    gives 17.9). pgvector is 0.8.1 on 17.9.
  - `rds.allowed_extensions` is unset by default, so nothing is restricted. The master user, who runs
    migrate, has rds_superuser.

**Local end-to-end** (`docker build --target prod`, then deploy/compose.prod.yaml against local Postgres):

| Step | Result |
|---|---|
| `check --deploy` with the placeholder key | exit 1, `clearpath.E001` |
| `run worker` with the placeholder key | exit 1, "Refusing to start" |
| `check --deploy` with a good config | `System check identified no issues (2 silenced)` |
| migrate | OK |
| `up -d --wait` | web healthy, worker healthy, beat up, redis healthy |
| `/api/health` | `{"status": "ok", "database": true}` |
| smoke.sh, Django-side checks | all pass |
| smoke.sh, SPA and static checks | fail as expected (they live in S3) |

### 7. Smoke test

`deploy/smoke.sh https://<domain>` checks:
1. `/api/health` returns 200 with `status ok` and `database true`, and carries Django's HSTS header. This
   proves `CloudFront-Forwarded-Proto` reaches Django.
2. `/` and `/queue` return the SPA's index.html.
3. `/static/admin/css/base.css` returns 200.
4. `/demo-partners/lendcompare/` returns Django HTML, not index.html. That proves the CloudFront behavior.
5. `/_allauth/browser/v1/config` lists email login and `is_open_for_signup: false`, with a `Secure`
   csrftoken cookie.
6. `/api/me` signed out returns 401.
7. A cross-origin login POST gets 403 (CSRF).

It runs every check, prints `FAIL <why>` plus the start of the body for each failure, and exits 1 if any
failed.

### Extra: public signup was open

`GET /_allauth/browser/v1/config` on main reports `"is_open_for_signup": true`. A probe on main returned
the following:
- `POST /_allauth/browser/v1/auth/signup {"email": "stranger@evil.example", ...}` gave **200** with
  `is_authenticated: true`.
- `/api/me` then gave 200 with `roles: []`.

The settings comment said "no public signup", but nothing enforced it. The hosted demo is public (geo US).
`accounts/adapter.py` returns False from `is_open_for_signup`. That's what headless checks
(`allauth/headless/account/views.py:157`), and the result is now 403. Test:
`accounts/tests/test_auth.py::test_public_signup_is_closed`. Admin provisioning (`accounts/api.py`) and
the demo seed create users directly, so they're unaffected (accounts and demo tests pass).

## Verification

| Command | Result |
|---|---|
| `pytest -q` (full backend) | 1829 passed, 3 deselected |
| `ruff check .`, `ruff format --check .`, `pyrefly check` | clean, `0 errors` |
| `makemigrations --check`, `check --fail-level WARNING` (dev) | no changes, no issues |
| `collectstatic --noinput` on prod settings with only CI's two env vars | 144 files, exit 0 |
| `shellcheck deploy/*.sh` | clean |
| `terraform fmt -check -recursive`, `validate` | exit 0, valid |
| `AWS_PROFILE=clearpath terraform plan -lock=false` | **`Plan: 76 to add, 0 to change, 0 to destroy.`** |
| local e2e (above) | as listed |

**Plan delta.** Main (with #39) already plans 76 to add: 74 plus `random_password.demo_user` and its SSM
parameter. This branch adds no resources. The only difference is inside the to-be-created
`aws_iam_role_policy.app`: `DocumentsReadWrite` is `GetObject, PutObject, AbortMultipartUpload` instead of
`GetObject, PutObject, DeleteObject`. Nothing exists yet, so it's all "add".

New dependencies:
- `django-storages[s3]>=1.14.6`, which brings boto3 1.43.118.
- dev group: `moto[s3]>=5.2.4`.
- botocore pins `python-dateutil<3`, so uv moved it from 3.0.0 to 2.9.0.post0. Its only other user is
  Celery, which is fine with it.

## Runbook (orchestrator)

Prereqs: this PR merged to main; Terraform ≥ 1.11; AWS profile `clearpath`; session-manager-plugin; run
from the US. `cd infra/main` throughout.

**1. Apply** (~20–25 min, mostly the VPC origin and the distribution):
```sh
terraform init
terraform plan -out=main.tfplan      # expect: Plan: 76 to add, 0 to change, 0 to destroy
terraform apply main.tfplan
```
Merging to main doesn't deploy yet: every Deploy job is skipped while `DEPLOY_ROLE_ARN` is unset.

**2. SSM values by hand.**

Set the Anthropic key. The parameter only exists after apply, holding Terraform's `value_wo` placeholder.
Never bump `value_wo_version`.
```sh
read -rs KEY   # paste the sk-ant-... key, Enter
aws ssm put-parameter --profile clearpath --region us-east-1 \
  --name /clearpath/prod/ANTHROPIC_API_KEY --type SecureString --overwrite --value "$KEY"
unset KEY
```

Read the demo password and hand it to Spencer for 1Password and evaluators:
```sh
aws ssm get-parameter --profile clearpath --region us-east-1 \
  --name /clearpath/prod/DEMO_USER_PASSWORD --with-decryption --query Parameter.Value --output text
```

Sanity check: names only, never values.
```sh
aws ssm get-parameters-by-path --profile clearpath --region us-east-1 --path /clearpath/prod \
  --query 'Parameters[].Name' --output text
```
Expect 13 names: ANTHROPIC_API_KEY, AWS_DEFAULT_REGION, DEMO_USER_PASSWORD, DJANGO_ALLOWED_HOSTS,
DJANGO_CSRF_TRUSTED_ORIGINS, DJANGO_SECRET_KEY, DOCUMENTS_BUCKET, FRONTEND_BASE_URL, POSTGRES_DB,
POSTGRES_HOST, POSTGRES_PASSWORD, POSTGRES_PORT and POSTGRES_USER. The two `deploy/` inputs sit one level
down, so this non-recursive call doesn't show them.

**3. Box ready.** user_data installs docker and compose at first boot, and usually finishes long before
the VPC origin does. To confirm:
```sh
aws ssm describe-instance-information --profile clearpath --region us-east-1 \
  --filters "Key=InstanceIds,Values=$(terraform output -raw app_instance_id)" --query 'InstanceInformationList[].PingStatus'
# ["Online"]
```

**4. GitHub variables** (DEPLOY_ROLE_ARN last: it's the switch):
```sh
gh variable set ECR_REPOSITORY_URL         --body "$(terraform output -raw ecr_repository_url)"
gh variable set APP_INSTANCE_ID            --body "$(terraform output -raw app_instance_id)"
gh variable set FRONTEND_BUCKET            --body "$(terraform output -raw frontend_bucket)"
gh variable set CLOUDFRONT_DISTRIBUTION_ID --body "$(terraform output -raw cloudfront_distribution_id)"
gh variable set DEPLOY_ROLE_ARN            --body "$(terraform output -raw deploy_role_arn)"
```

**5. First deploy** (this is also the first live test of the OIDC `sub` for `workflow_dispatch`):
```sh
gh workflow run deploy.yaml --ref main
gh run list --workflow deploy.yaml --limit 1     # get the run id
gh run watch <run-id> --exit-status --interval 10
```

The SSM step's stdout should show, in order:
1. `render-env: wrote N keys`
2. `System check identified no issues (2 silenced).`
3. the migrate output
4. `Seeded <n> items, <m> legacy tracker items, <p> people.`. This is the first deploy only; the seed
   writes the demo attachments to S3.
5. `deploy: <image> is up and healthy`

Then the frontend sync and invalidation run.

If it fails at the check step with `clearpath.E001`, the key isn't set (step 2). Fix it and re-run
`gh workflow run`.

**6. Smoke and one-off verifications**:
```sh
D="https://$(terraform output -raw cloudfront_domain)"
../../deploy/smoke.sh "$D"                 # all "ok", exit 0
../../deploy/verify-client-ip.sh "$D"      # OK = CloudFront overwrites a spoofed CloudFront-Viewer-Address
```
`verify-client-ip.sh` locks your IP out of login for about a minute.

On the box (`aws ssm start-session ... --target <instance>`, then `sudo -i; cd /srv/clearpath`):
```sh
docker compose -f compose.prod.yaml ps      # web/worker healthy, beat/redis up
docker compose -f compose.prod.yaml exec web python manage.py shell -c \
  "from django.db import connection as c; k=c.cursor(); k.execute('show max_connections'); print(k.fetchone())"
ss -tn sport = :8000                         # which peer IPs CloudFront's VPC origin uses (infra report open risk)
```
Record `max_connections` here; the budget assumes ≥ 50.

Then sign in as `admin@clearpath.demo` with the SSM password. Open an item with an attachment and download
it: that streams from S3. Request an evidence pack.

**7. Rollback**:
- **Failure before `up`** (render-env, check, migrate, seed): nothing to do. The old containers still
  serve. Fix the cause and redeploy.
- **Failure at `up --wait` or the health check**: prod is down on the new image. Re-run all jobs of the
  last good Deploy run (it rebuilds that commit and reuses its ECR image). Or, from Session Manager:
  `sudo /srv/clearpath/deploy.sh <ecr_repository_url>:<good-sha>`.
  - On the very first deploy there's no previous release. Read
    `docker compose -f compose.prod.yaml logs web worker --tail 100` and fix forward.
- **Migrations are not reversed.** They must stay expand-only.
- **Client-IP fallback** (if `verify-client-ip.sh` fails): delete `ALLAUTH_TRUSTED_CLIENT_IP_HEADER` from
  prod.py, merge, and deploy. allauth then keys on REMOTE_ADDR from uvicorn's `--forwarded-allow-ips`.

## For the orchestrator to decide or know

1. **Public signup fix is in this PR** (security, small). Say if you'd rather split it out. The SPA never
   offered signup, so there's no UI change.
2. **No `DeleteObject` for the app.** A future "expire old export files" job (G follow-up) needs it back,
   scoped to `exports/*`. Reset demo leaves the previous seed's attachment objects in S3 as orphans
   (pennies; versioned bucket).
3. **The `sk-ant-` prefix requirement** in E001 rejects a wrongly pasted secret. If Anthropic ever changes
   the key format, deploys stop with E001 until the check is relaxed.
4. **Optional, not done**: an S3 gateway VPC endpoint (free) would take document traffic off the NAT
   ($0.045/GB). It's one `aws_vpc_endpoint` plus a route-table association, worth it only if files get
   big.
5. **Ledger cleanup**: Rulings line 51 ("seed_demo runs after migrate on container start") contradicts
   line 42 and the merged deploy.sh (seed in deploy.sh). The later ruling, deploy.sh, is what shipped.
