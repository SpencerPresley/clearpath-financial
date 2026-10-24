# Report: infra-terraform

Branch `infra/terraform`. Written, validated and planned. The only thing applied is the state bucket
(`infra/bootstrap`, 7 resources). It was not changed or re-applied during the review round.

This report reflects the post-review state. Review findings and how each was resolved:
`docs/plan/reviews/infra-terraform.md` → "Resolutions".

## What was built

- `infra/bootstrap/`: the state bucket `clearpath-tfstate-381491937698`. It's versioned, SSE-S3,
  BucketOwnerEnforced, has public access blocked and a TLS-only policy, expires noncurrent versions
  after 90 days, and has `prevent_destroy`. Its own state is local and gitignored. **Applied.**
- `infra/main/`: one flat stack. I didn't use modules: there's one environment and nothing is reused,
  so a module would only add indirection.
  - `network.tf`: VPC `10.20.0.0/16`, 2 public and 2 private subnets in us-east-1a/b, an IGW, one NAT,
    and the default SG emptied.
  - `app.tf`: the app server.
    - t3.medium, AL2023 x86_64. Private subnet, no public IP, no key pair.
    - IMDSv2 required, hop limit 2. Encrypted 30 GB gp3 root.
    - user_data installs docker, jq and compose v5.6.1 (sha256-checked), and sets up log rotation.
    - SG: inbound 8000 only from the CloudFront origin-facing prefix list; all egress.
    - Instance role: SSM core, ECR pull (repo-scoped), `ssm:GetParameter*` on `parameter/clearpath/*`,
      and R/W on the documents bucket.
    - It also has `ec2:GetManagedPrefixListEntries`, scoped to `pl-3b927c52`.
  - `database.tf`: PG `17`, db.t4g.micro, gp3 20 GB (autoscales to 100), encrypted, private.
    - Single-AZ, pinned to the app subnet's AZ. SG ingress only from the app SG.
    - Backups kept 7 days, deletion protection off.
    - **Final snapshot by default** (`clearpath-prod-final`). Extended Support disabled.
  - `storage.tf`: frontend bucket (OAC-only), documents bucket (versioned, SSE-S3, public access
    blocked, TLS-only), and ECR `clearpath/backend` (IMMUTABLE, scan on push, keeps the last 20).
  - `edge.tf`: OAC, the VPC origin (30-minute timeouts), the SPA rewrite function on the default
    behavior only, and the distribution.
    - Behaviors `/api/*`, `/_allauth/*`, `/accounts/*`, `/django-admin/*` go to the VPC origin.
      They use CachingDisabled + AllViewerAndCloudFrontHeaders-2022-06, are https-only, and allow
      all methods.
    - Geo allowlist US. PriceClass_100. **IPv4 only.** SecurityHeadersPolicy on the SPA behavior.
    - Optional two-phase ACM path for a custom domain.
  - `waf.tf`: CLOUDFRONT-scope web ACL with IpReputation, Common (`SizeRestrictions_BODY` set to
    Count) and KnownBadInputs.
    - Plus a per-IP rate rule, 50 per 5 minutes, on `POST AND (path ~ ^/_allauth/[^/]+/v1/auth/ OR
      path STARTS_WITH /django-admin/login)`.
  - `waf_logs.tf`: an `aws-waf-logs-clearpath-381491937698` bucket with 14-day expiry, the documented
    delivery policy, and TLS-only.
    - Logging config with `cookie`, `authorization`, `x-csrftoken` and `x-session-token` redacted.
  - `config.tf`: SSM parameters under `/clearpath/prod/`.
    - SecureStrings: `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` (random_password).
    - `ANTHROPIC_API_KEY` uses write-only `value_wo` with a placeholder and `value_wo_version = 1`,
      so the real key is never in state.
    - Plain config Strings, plus `/deploy/` inputs for render-env.sh.
  - `github.tf`: OIDC provider and a deploy role.
    - Trust: `aud = sts.amazonaws.com` and `sub` StringEquals
      `repo:SpencerPresley@153392395/clearpath-financial@1431827457:ref:refs/heads/main`. Both come
      from variables `github_oidc_sub_prefix` and `github_deploy_ref`.
    - Permissions:
      - ECR push on the repo.
      - SendCommand limited to `AWS-RunShellScript` and to instances tagged `DeployTarget=clearpath-app`.
      - GetCommandInvocation and ListCommandInvocations.
      - Frontend-bucket sync.
      - Invalidation on the one distribution.
- `deploy/compose.prod.yaml`: web (uvicorn), worker, beat, and redis (digest-pinned, no persistence).
  The backend image comes from `${BACKEND_IMAGE}`.
- `deploy/render-env.sh`: renders SSM → `/srv/clearpath/.env` (0600, atomic, rejects quotes and
  newlines), then appends `FORWARDED_ALLOW_IPS` and `BACKEND_IMAGE`.
- `deploy/deploy.sh`: render, ECR login, pull, migrate, `up -d --wait`, then require
  `database == true`, then prune.
- `.github/workflows/deploy.yaml`: three jobs. All are skipped unless `vars.DEPLOY_ROLE_ARN` is set
  and `github.ref == refs/heads/main`.
  - `build-backend`: docker build, collectstatic, `docker save` → artifact.
  - `build-frontend`: npm ci and build → artifact.
  - `deploy`: needs both, and is the **only** job with `id-token: write`.
    - It downloads the artifacts, assumes the role, then loads and pushes the image (skipped if that
      SHA is already in ECR).
    - It runs the SSM deploy and polls to a terminal status, retrying up to 5 transient API errors in
      a row.
    - Then s3 sync and invalidate.
  - Triggers: push to main on `backend/**`, `frontend/**`, `deploy/**` and the workflow file, or
    `workflow_dispatch`.
- `infra/README.md`: bootstrap, plan/apply (`main.tfplan`), repo variables, what gates a deploy, the
  Anthropic key, rollback, runtime config, shell access, custom domain, destroy, logs, and cost.

## Deviations from the brief (and why)

1. **Origin request policy is `AllViewerAndCloudFrontHeaders-2022-06`, not `AllViewerExceptHostHeader`.**
   AllViewerExceptHostHeader replaces Host with the origin domain. For an EC2 VPC origin that domain
   is the instance's `ip-10-…ec2.internal`, so Django would need it in `ALLOWED_HOSTS` and would build
   URLs with it. The 2022-06 policy forwards the viewer Host and explicitly includes
   `CloudFront-Forwarded-Proto`.
   Source: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html
   The reviewer confirmed this independently via `aws cloudfront list-origin-request-policies`.
2. **`--forwarded-allow-ips` is the VPC CIDR plus the live CloudFront origin-facing CIDRs.**
   - Not `*`: in uvicorn 0.54.0, always-trust takes the leftmost XFF entry, which the client controls.
     allauth 65.x rate limits key on `REMOTE_ADDR`, so that value must not be spoofable.
   - Not the VPC CIDR alone: the VPC-origins doc implies the peer is a CloudFront public IP.
   - Refreshed on every deploy.
3. **Migrate runs before `up`.** The cost is that migrations must stay expand-only.
4. **AZs exclude `use1-az3`.** VPC origins don't support it.
5. **WAF `SizeRestrictions_BODY` is set to Count.** Otherwise it blocks any body over 8 KB.
6. **Django admin static files are served from S3 under `static/`.**
7. **ECR tags are IMMUTABLE git SHAs.**
8. **Deploy trust is pinned to `ref:refs/heads/main`, not `environment:production`** (orchestrator
   ruling on review B1/S1).
   - This repo issues immutable OIDC subjects, and the old `repo:OWNER/REPO:…` string would never
     match.
   - On GitHub Free a private repo gets no environment protection or branch protection, so an
     environment pin would gate nothing.
   - **`docs/decisions.md` → Hosting → Deploy step 2 still says
     `repo:SpencerPresley/clearpath-financial:environment:production`.** That file isn't in my paths,
     so I left it; it needs updating to match.
9. **IPv6 is off on the distribution.** The per-IP rate rule would otherwise be per-address for
   IPv6, and a /64 gives an attacker plenty of addresses (review N11).

## Observed OIDC subject (empirical)

A throwaway workflow `.github/workflows/oidc-sub-probe.yaml` ran on push to `infra/terraform`
(run 40094647323). It had `id-token: write`, fetched a token for audience `sts.amazonaws.com`, and
printed only the decoded `sub`:

```
sub=repo:SpencerPresley@153392395/clearpath-financial@1431827457:ref:refs/heads/infra/terraform
```

This confirms the format `<sub_claim_prefix>:ref:refs/heads/<branch>` for a non-environment job.
The trust policy therefore pins `…@1431827457:ref:refs/heads/main`, which the plan output confirms.
The probe workflow was deleted in the next commit.

## Verification (commands run, actual results)

| Command | Result |
|---|---|
| `terraform -chdir=infra fmt -check -recursive` | exit 0 |
| `terraform -chdir=infra/main validate`, `-chdir=infra/bootstrap validate` | `Success! The configuration is valid.` (both) |
| `terraform plan` (main, defaults) | **`Plan: 74 to add, 0 to change, 0 to destroy.`** (was 67; +7 for WAF logging: bucket, ownership, PAB, SSE, lifecycle, policy, logging config). No warnings. |
| Plan details checked | Trust `sub` = `repo:SpencerPresley@153392395/clearpath-financial@1431827457:ref:refs/heads/main`. `anthropic_api_key` has `value = null`, `value_wo_version = 1`. RDS `availability_zone = us-east-1a`, `skip_final_snapshot = false`, `final_snapshot_identifier = clearpath-prod-final`. `is_ipv6_enabled = false`. Prefix-list permission on `arn:aws:ec2:us-east-1:aws:prefix-list/pl-3b927c52`. |
| `terraform plan -var custom_domain=… -var attach_custom_domain=true` (before review) | `Plan: 69 to add` |
| `shellcheck deploy/*.sh` | clean |
| `actionlint` (rhysd/actionlint container) on all workflows | clean |
| render-env.sh against stubbed `aws`/`curl` (re-run this round) | good case writes 5 keys, mode 0600, with `$ # \` and spaces literal. Values containing `'` or a newline: exit 1, no file written. |
| `docker compose -f compose.prod.yaml config --images` with that .env (re-run) | backend image interpolated; `redis:7-alpine@sha256:57e4255c…` |

### Checked against docs, schema or source

- **Provider argument names:** hashicorp/aws 6.70.0 `terraform providers schema -json`.
  - New this round: `aws_ssm_parameter.value_wo` (write_only, sensitive) and `value_wo_version`.
  - `aws_wafv2_web_acl_logging_configuration{log_destination_configs, redacted_fields.single_header}`.
  - Scope-down nesting: `and → statement → or → statement` allows only leaf statements, hence the
    regex for the allauth paths.
- **Write-only arguments need Terraform ≥ 1.11.** `required_version` is now `>= 1.11` in both stacks.
- **`ec2:GetManagedPrefixListEntries` supports the `prefix-list` resource type.** Source: the AWS
  programmatic service reference, `servicereference.us-east-1.amazonaws.com/v1/ec2/ec2.json`.
- **WAF S3 logging:** the bucket must be named `aws-waf-logs-*`; SSE-S3 or customer KMS is required
  (not AWS-managed KMS); the delivery policy statements are copied from
  https://docs.aws.amazon.com/waf/latest/developerguide/logging-s3.html.
- **New action SHAs:** upload-artifact v7.0.2 `cf430e030ddbb5b0abf93d22962f4752f3646cd9` and
  download-artifact v8.0.2 `9000827ccba6bdab643e8b6fd33ac0654aef8333`, both type `commit` per
  `gh api …/git/ref/tags/<tag>`.
- **redis digest:** `docker buildx imagetools inspect redis:7-alpine` gave index
  `sha256:57e4255cc971b1c8d6f8a6ca283ac01bc3ecdd914273ef6bfaede87aaecd6541`.
- **Unchanged from round 0:**
  - VPC-origin requirements, managed policy IDs and contents, and SizeRestrictions_BODY = 8 KB.
  - The CloudFront prefix list weighs 55 against the 60-rule SG quota.
  - VPC origin default timeout is 15 min; I set 30 min.
  - CachingDisabled has compression off.
  - RDS PG 17 extensions, configure-aws-credentials / checkout / setup-node SHAs, and the compose
    checksum.

## Cost

About **$93/month** always-on; table in `infra/README.md`. WAF logging to S3 adds pennies at this
traffic (estimate). The biggest lines are NAT $33.10, EC2 $30.37, RDS $11.68 + $2.30, WAF ~$9 and
public IPv4 $3.65.

## App follow-ups (not in my paths)

- **allauth rate-limit counters need a shared cache.** There is no `CACHES` in settings, so allauth's
  counters live in per-process LocMemCache: `--workers=2` doubles the effective limit, and every
  deploy resets it. Point `CACHES` at the compose Redis (`redis://redis:6379/1`).
- **Django admin login has no MFA and no app-level throttle.** Options: wrap it with allauth's
  `secure_admin_login` (check how it behaves under `HEADLESS_ONLY = True`), or require an
  allauth-MFA'd session for admin. WAF now rate-limits the POSTs (S4), but that's the only control.
- `ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "CloudFront-Viewer-Address"` is an alternative to relying on
  uvicorn. The value is `ip:port`; check `clean_client_ip` handles it.
- Read `DOCUMENTS_BUCKET` in `Env` when uploads land.
- asgi.py and celery.py default to dev settings. The image and compose override this, but it's
  fragile.
- `docs/decisions.md` Deploy step 2: update the pinned `sub` (deviation 8).

## Open risks

- **Deploy trust = "can push to main".** No environment, reviewer or branch protection is available on
  this plan. A leaked token with push access, or an agent session pushing to main, deploys. Upgrading
  to Pro would be needed for environment gates (an orchestrator or user call; it costs money).
- **Source IP at the origin is unverified.** Run `ss -tn sport = :8000` after the first apply. The
  config works either way.
- **origin_read_timeout is 60s:** SSE streams need keepalives at least every 60 seconds.
- **WAF `CrossSiteScripting_BODY` / `GenericRFI_BODY` may false-positive** on marketing copy. WAF logs
  now make this diagnosable; override the specific rule to Count if it happens.
- **`random_password` results (Django secret, DB password) are still in state.** The Anthropic key no
  longer is. `password_wo` / ephemeral resources could remove the rest later.
- **Final snapshot name is fixed**, so a second destroy needs the old snapshot deleted first
  (README).
- **CloudFront function:** a deep link whose last segment contains a dot isn't rewritten.
- **Instance `ignore_changes = [ami, user_data]`:** changes need `-replace`, which also redeploys the
  VPC origin.
- **Not applied, so not exercised end to end:** the deploy workflow (artifact handoff, SSM polling),
  compose on AL2023, IAM as written, and WAF log delivery.

## Review notes accepted without change

- **N1:** AmazonSSMManagedInstanceCore grants `ssm:GetParameter(s)` on `*`, so the role's
  `/clearpath/*` scoping is cosmetic for those two actions. It does scope `GetParametersByPath`. No
  other parameters exist in the account. Accepted.
- **N3:** hop limit 2 lets containers reach IMDS (needed for the instance role), so an SSRF in Django
  could fetch role credentials. IMDSv2 blunts GET-only SSRF. Accepted design tradeoff; it belongs in
  the decisions doc.
- **N6:** the inline payload is about 10 KB of base64. No documented SendCommand parameter quota was
  found; the first deploy proves it, and the fallback is shipping `deploy/` via S3.
- **N12:** `/api` and `/django-admin` without a trailing slash get the SPA's index.html. Cosmetic.
- **N14:** cost is accepted as is; the README already names the NAT-instance alternative.
