# Report: infra-terraform

Branch `infra/terraform`. Written, validated and planned. The only thing applied is the state bucket
(`infra/bootstrap`, 7 resources).

## What was built

- `infra/bootstrap/`: the state bucket `clearpath-tfstate-381491937698`. It's versioned, SSE-S3,
  BucketOwnerEnforced, has public access blocked and a TLS-only policy, expires noncurrent versions
  after 90 days, and has `prevent_destroy`. Its own state is local and gitignored. **Applied.**
- `infra/main/`: one flat stack. I didn't use modules: there's one environment and nothing is reused,
  so a module would only add indirection. Files are split by concern:
  - `network.tf`: VPC `10.20.0.0/16` with 2 public and 2 private subnets in us-east-1a/b, an IGW, one
    NAT, and the default SG emptied.
  - `app.tf`: t3.medium, AL2023 x86_64 (AMI from the public SSM parameter). Private subnet, no public
    IP, IMDSv2 required with hop limit 2, encrypted 30 GB gp3 root, no key pair. user_data installs
    docker, jq and compose v5.6.1 (sha256-checked), sets up log rotation and creates `/srv/clearpath`.
    - SG: inbound 8000 only from `com.amazonaws.global.cloudfront.origin-facing` (pl-3b927c52); all
      egress.
    - Instance role: SSM core, ECR pull scoped to the repo, `ssm:GetParameter*` on
      `parameter/clearpath/*`, R/W on the documents bucket, and `ec2:GetManagedPrefixListEntries`
      (see the uvicorn section).
  - `database.tf`: PG `17` (major-only, auto minor upgrade), db.t4g.micro, gp3 20 GB (autoscaling to
    100), encrypted, private, single-AZ. SG ingress only from the app SG. Backups kept 7 days,
    deletion protection off, `skip_final_snapshot` set by a variable (default true). Extended Support
    is explicitly disabled.
  - `storage.tf`:
    - frontend bucket: OAC-only policy keyed on the distribution ARN.
    - documents bucket: versioned, SSE-S3, public access blocked, TLS-only, and incomplete multipart
      uploads aborted after 7 days.
    - ECR `clearpath/backend`: IMMUTABLE tags, scan on push, keeps the last 20 images.
  - `edge.tf`: OAC, the VPC origin, the SPA rewrite CloudFront Function (`functions/spa-rewrite.js`,
    viewer-request, default behavior only) and the distribution.
    - Behaviors `/api/*`, `/_allauth/*`, `/accounts/*`, `/django-admin/*` go to the VPC origin with
      Managed-CachingDisabled and Managed-AllViewerAndCloudFrontHeaders-2022-06, https-only, all
      methods.
    - Geo allowlist is US. PriceClass_100, http2and3.
    - Managed-SecurityHeadersPolicy is on the SPA behavior.
    - Optional two-phase ACM path for a custom domain.
  - `waf.tf`: CLOUDFRONT-scope web ACL with IpReputation, Common and KnownBadInputs, plus a per-IP
    rate rule. The rate rule counts POSTs whose path starts with `/_allauth/` and contains `/v1/auth/`
    (login, 2FA, password reset, login-by-code), 50 per 5 minutes.
  - `config.tf`: SSM parameters under `/clearpath/prod/`.
    - SecureStrings: `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` (from `random_password`), and
      `ANTHROPIC_API_KEY` (placeholder, `ignore_changes = [value]`).
    - Plain Strings: `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `FRONTEND_BASE_URL`,
      `POSTGRES_HOST/PORT/DB/USER`, `DOCUMENTS_BUCKET`, `AWS_DEFAULT_REGION`.
    - Inputs for render-env.sh go under `/deploy/`.
  - `github.tf`: OIDC provider and a deploy role.
    - Trust: `aud=sts.amazonaws.com`, and `sub` StringEquals
      `repo:SpencerPresley/clearpath-financial:environment:production`.
    - Permissions:
      - ECR push and DescribeImages on the repo.
      - `ssm:SendCommand` limited to the `AWS-RunShellScript` document, and to instances tagged
        `DeployTarget=clearpath-app` via `ssm:resourceTag/DeployTarget`.
      - `ssm:GetCommandInvocation` and `ssm:ListCommandInvocations`.
      - s3 sync on the frontend bucket.
      - `cloudfront:CreateInvalidation` and `cloudfront:GetInvalidation` on the distribution.
  - `outputs.tf`: everything requested, plus the custom-domain DNS records.
- `deploy/compose.prod.yaml`: web (uvicorn), worker, beat and redis (no persistence). Images come
  from `${BACKEND_IMAGE}`. There's no Postgres. `.env` is used both for interpolation and as each
  container's environment.
- `deploy/render-env.sh`: turns `/clearpath/prod/*` (non-recursive) into `KEY='value'` lines, mode
  0600, written atomically. It rejects quotes and newlines, then appends `FORWARDED_ALLOW_IPS` and
  `BACKEND_IMAGE`.
- `deploy/deploy.sh` (on the server, extra to the brief): render env, ECR login, pull, `migrate`,
  `up -d --wait`, then a health check that requires `database: true`, then prune.
- `.github/workflows/deploy.yaml`:
  - The job is skipped when `vars.DEPLOY_ROLE_ARN` is empty. It runs in environment `production`
    with OIDC.
  - It builds the image, or reuses it if that SHA is already in ECR, and pushes it.
  - It runs collectstatic into a container, builds the frontend, then sends the SSM command
    (deploy/ is shipped inline as base64) and polls to a terminal status. Anything but `Success`
    fails the job.
  - Then: s3 sync (hashed assets immutable and never deleted; the rest `no-cache` with `--delete`;
    Django static under `static/`), invalidate, and wait.
- `infra/README.md`: bootstrap, plan/apply, repo variables, the Anthropic key, shell access, custom
  domain, destroy, and cost.

## Deviations from the brief (and why)

1. **Origin request policy is `AllViewerAndCloudFrontHeaders-2022-06`, not `AllViewerExceptHostHeader`.**
   AWS docs say AllViewerExceptHostHeader is meant for API Gateway and Lambda URL origins, and that it
   replaces Host with the origin domain. For an EC2 VPC origin that domain is the instance's
   `ip-10-20-10-x.ec2.internal`. Django would then have to list a private hostname in
   `ALLOWED_HOSTS`, and absolute URLs would use it too. The 2022-06 policy forwards the viewer's Host,
   and it explicitly includes `CloudFront-Forwarded-Proto` (which prod.py's `SECURE_PROXY_SSL_HEADER`
   needs) and `CloudFront-Viewer-Address`.
   Source: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-origin-request-policies.html
2. **`--forwarded-allow-ips` is the VPC CIDR plus the live CloudFront origin-facing CIDRs, not the
   VPC CIDR alone and not `*`.**
   - The VPC-origins doc lets the origin SG allow the CloudFront *public* prefix list. It also says
     outbound NACLs must allow return traffic "to the CloudFront origin-facing IP ranges". Both imply
     the TCP peer uvicorn sees is a CloudFront public IP. If so, a VPC-CIDR-only value would quietly
     disable proxy-header handling.
   - `*` is worse. In uvicorn 0.54.0's `proxy_headers.py`, `always_trust` returns the *leftmost* XFF
     entry, which the client controls. The default allauth 65.x client IP is `REMOTE_ADDR`
     (`allauth/core/internal/httpkit.py:get_client_ip`), so allauth's login rate limits would key on
     a spoofable value.
   - With the CIDR list, uvicorn walks XFF from right to left and stops at CloudFront's appended
     viewer IP.
   - render-env.sh re-reads the prefix list on every deploy.
   - Including the VPC CIDR covers the other hypothesis, where the peer is the ENI's private IP.
3. **Migrate runs before `up`, not after.** If `up` ran first, new code would serve against the old
   schema until migrations finished. Running migrate first requires backward-compatible
   (expand/contract) migrations, which is the standard tradeoff.
4. **Availability zones exclude `use1-az3`.** CloudFront VPC origins aren't supported there (it's
   us-east-1e in this account). The selection is by zone ID.
5. **WAF `SizeRestrictions_BODY` is set to Count.** It blocks any body over 8 KB (AWS baseline
   rule-group docs), which would block image-mockup uploads and long submissions.
6. **Django admin static files go to S3.** Nothing on the server serves `/static/`, and
   `/django-admin/*` is routed to Django, so the workflow runs collectstatic and syncs to
   `s3://frontend/static/`. That path is served by the default behavior; the rewrite function leaves
   it alone because the files have extensions.
7. **ECR tags are IMMUTABLE.** Tags are git SHAs. Re-running a deploy reuses the existing image
   instead of failing the push.

## Verification (commands run, actual results)

| Command | Result |
|---|---|
| `terraform -chdir=infra fmt -check -recursive` | exit 0 |
| `terraform -chdir=infra/main validate` / `-chdir=infra/bootstrap validate` | `Success! The configuration is valid.` (both) |
| `terraform plan` (bootstrap), then `apply` | `Apply complete! Resources: 7 added` |
| `terraform plan` (main, defaults) | `Plan: 67 to add, 0 to change, 0 to destroy.` No warnings. |
| `terraform plan -var custom_domain=clearpath.spencerpresley.com -var attach_custom_domain=true` | `Plan: 69 to add` (cert + validation), aliases and ACM cert set |
| `terraform plan -var attach_custom_domain=true` (no domain) | fails the variable validation, as intended |
| `shellcheck deploy/*.sh` | clean |
| `actionlint` (rhysd/actionlint container) on deploy.yaml | clean |
| render-env.sh against stubbed `aws`/`curl` (scratch harness) | Writes 5 keys, mode 0600. `$`, `#`, `\`, and spaces stay literal. A value with `'` or a newline exits 1 and leaves no file. |
| `docker compose -f compose.prod.yaml config` with that rendered .env | Interpolates `--forwarded-allow-ips=10.20.0.0/16,...` and `image:`. Secret values stay literal (`ab$$c#d…` is compose's escaped display of `ab$c#d…`). |

Plan by type (67 total):
- 14 aws_ssm_parameter
- 4 each: aws_subnet, aws_route_table_association
- 2 each: aws_s3_bucket and each S3 sub-resource type (policy, PAB, ownership, SSE), aws_iam_role,
  aws_iam_role_policy, aws_route, aws_route_table, aws_security_group,
  aws_vpc_security_group_ingress_rule, random_password
- 1 each: VPC, IGW, EIP, NAT, default SG, egress rule, instance, instance profile, role-policy
  attachment, DB instance, DB subnet group, ECR repo + lifecycle, OIDC provider, versioning,
  lifecycle config, CloudFront distribution, function, OAC, VPC origin, WAF web ACL

Data sources resolved at plan time:
- AZs: a, b, c, d, f (az3/us-east-1e excluded); a and b are used.
- AMI `ami-08c46876c64a927b8`.
- Prefix list `pl-3b927c52` (49 entries).
- Managed policy IDs: CachingDisabled `4135ea2d…`, CachingOptimized `658327ea…`,
  AllViewerAndCloudFrontHeaders `33f36d7e…`, SecurityHeaders `67f7725c…`.

### What was checked against docs or schema

- **Provider resource and argument names:** checked against `terraform providers schema -json` for
  the installed hashicorp/aws **6.70.0** (the latest on the registry today). That covers
  `aws_cloudfront_vpc_origin.vpc_origin_endpoint_config{arn,http_port,https_port,name,
  origin_protocol_policy,origin_ssl_protocols{items,quantity}}`, `origin.vpc_origin_config
  {vpc_origin_id,origin_read_timeout,origin_keepalive_timeout}`, WAF `rate_based_statement
  {limit,evaluation_window_sec,aggregate_key_type,scope_down_statement.and_statement}`,
  `rule_action_override`, `aws_db_instance.engine_lifecycle_support`, and
  `aws_iam_openid_connect_provider.thumbprint_list` (optional).
- **`use_lockfile`:** Terraform S3 backend docs via ctx7 (`/websites/developer_hashicorp_terraform`).
  DynamoDB locking is deprecated there.
- **VPC origin requirements:** IGW required, private subnet, SG option 1 is the prefix list,
  us-east-1 excludes use1-az3, and for EC2 the domain is the private IP DNS name. Source:
  https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html
- **RDS PG 17.11 extensions:** btree_gist 1.7, pg_trgm 1.6, pgvector 0.8.2 (RDS PostgreSQL
  extensions release notes).
- **Pinned action SHAs:** looked up with `gh api …/git/ref/tags/<tag>`, all type `commit`:
  configure-aws-credentials v6.3.0 `e1253824e5c10ff9df46874f81ed3ec929e19cfd`, checkout v7.0.1, and
  setup-node v7.1.0 (the same SHAs existing CI uses).
- **Compose v5.6.1 checksum:** the release asset digest matches the published `.sha256` file.

## Cost

About **$93/month** always-on (full table and sources in `infra/README.md`). The biggest lines are
NAT $33.10, EC2 $30.37, RDS $11.68 + $2.30 storage, WAF ~$9, and public IPv4 $3.65. Unit prices come
from the AWS Price List API. WAF's $5/ACL comes from the pricing page, and small items are estimates.

## Open risks

- **Source IP at the origin is unverified.** After the first apply, run `ss -tn sport = :8000` on the
  box (or check `request.META['REMOTE_ADDR']`) to confirm it's a CloudFront range. The config works
  either way. If it turns out to be a VPC ENI address, the CloudFront CIDRs in the list are just
  harmless extras.
- **App-side follow-ups (not in my paths):**
  - Set `ALLAUTH_TRUSTED_CLIENT_IP_HEADER = "CloudFront-Viewer-Address"` or keep relying on uvicorn.
    That header is `ip:port`; check that allauth's `clean_client_ip` handles it before switching.
  - Read `DOCUMENTS_BUCKET` in `Env` when uploads land.
  - asgi.py and celery.py default to dev settings. The image and compose set
    `DJANGO_SETTINGS_MODULE=config.settings.prod`, so it's fine, but it's fragile.
- **origin_read_timeout is 60s,** the default-quota maximum. SSE assistant streams need a byte (or
  keepalive comment) at least every 60s, or CloudFront cuts them.
- **WAF CommonRuleSet `CrossSiteScripting_BODY` and `GenericRFI_BODY` may false-positive** on
  marketing copy containing HTML or URLs with IP hosts. Watch the WAF sampled requests after launch;
  overriding them to Count for `/api/` is the fix.
- **AWS-RunShellScript parameter size:** deploy/ ships inline as base64, about 12 KB today. I didn't
  verify the SendCommand parameter size limit. If the scripts grow a lot, move them to S3.
- **First apply ordering:** the frontend bucket policy needs the distribution ARN, and the
  distribution needs the instance to be running before the VPC origin accepts it. Terraform's graph
  handles both, but the VPC origin can take ~15 min. Account-level surprises (CloudFront or VPC
  origin quotas on a new account) only show up at apply.
- **Secrets are in Terraform state** (random_password results, and the SSM values they produce). The
  state bucket is private, encrypted and TLS-only. `password_wo` and ephemeral resources could remove
  this later, but I chose not to: it adds complexity for a demo.
- **CloudFront function edge case:** a deep link whose last path segment contains a dot (e.g.
  `/users/jane.doe`) isn't rewritten and returns S3's 403. Current routes don't have this; keep SPA
  route segments dot-free or tighten the regex.
- **`ignore_changes = [ami, user_data]` on the instance:** user_data edits don't reach the running
  box. Use `terraform apply -replace=aws_instance.app`, which also redeploys the VPC origin (~15 min).
- **Not applied, so not exercised end to end:** the deploy workflow, SSM polling, compose on AL2023,
  and the IAM permissions as written. All of these get proven at the deploy wave.
