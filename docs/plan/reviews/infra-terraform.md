# Review: PR #16 "Infrastructure: Terraform for AWS hosting" (`infra/terraform` @ 4d65a1c)

**Verdict: don't merge yet. There is 1 blocker and 5 should-fix findings.** The blocker: the deploy role's OIDC trust policy can never match the token GitHub issues for this repo, so every deploy will fail at `AssumeRoleWithWebIdentity`. The Terraform itself is careful and most of the author's claims hold up (list under "Verified OK"). The problems are at the GitHub/AWS seam and in three claims the report makes that aren't true for this repo.

All line numbers refer to files on `origin/infra/terraform`.

---

## Blocker

### B1. OIDC `sub` condition uses the old subject format, and this repo issues immutable subjects
`infra/main/github.tf:26-30`, `infra/main/variables.tf:67-70`

**Evidence:**
- `gh api repos/SpencerPresley/clearpath-financial/actions/oidc/customization/sub` returns:
  ```json
  {"use_default":true,"use_immutable_subject":true,"sub_claim_prefix":"repo:SpencerPresley@153392395/clearpath-financial@1431827457"}
  ```
- The repo's `created_at` is `2026-10-24T04:55:34Z`. GitHub's OIDC reference says "repositories created after July 15, 2026 now use an immutable default subject format", with the syntax `repo:OWNER@OWNER-ID/REPO@REPO-ID:...` (https://docs.github.com/en/actions/reference/security/oidc).

**Failure:** the token's `sub` will be `repo:SpencerPresley@153392395/clearpath-financial@1431827457:environment:production`. The policy does `StringEquals` against `repo:SpencerPresley/clearpath-financial:environment:production`. The first run after `DEPLOY_ROLE_ARN` is set fails in `configure-aws-credentials` with `Not authorized to perform sts:AssumeRoleWithWebIdentity`, and every later run fails the same way. It fails closed, so this is not a security hole, but deploys never work.

**Fix:**
- Build the value from the immutable prefix. For example, set `github_repository` to `SpencerPresley@153392395/clearpath-financial@1431827457`, or add a `github_sub_prefix` variable and use `"${var.github_sub_prefix}:environment:${var.github_environment}"`. Add a comment pointing at the July 2026 cutover.
- Update the pinned-sub text in `docs/decisions.md` "Hosting" step 2 and in the report.
- Before the first real deploy, confirm the exact string. The GitHub docs give no immutable example for an environment-scoped job, so `...:environment:production` is inferred from the documented pattern, not quoted. To confirm, run a throwaway `workflow_dispatch` job with `environment: production` and `permissions: id-token: write`. It should fetch a token with `curl -sH "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com"` and print only the decoded payload's `sub`. The same run also settles S1.

---

## Should-fix

### S1. The "environment protection gates every deploy" premise doesn't hold on this repo's plan
`infra/main/github.tf:23-25`, `infra/README.md:56-57`, `.github/workflows/deploy.yaml:10,27`

**Evidence:**
- `gh api user` → `plan=free`.
- `gh repo view` → `"visibility":"PRIVATE"`.
- `gh api .../branches/main/protection` and `.../rulesets` both return `403 Upgrade to GitHub Pro or make this repository public`.
- `gh api .../environments` → `total_count: 0`.
- GitHub's environments page: "Users with GitHub Free plans can only configure environments for public repositories", and "Running a workflow that references an environment that does not exist will create an environment with the referenced name … no protection rules".

**Failure:** none of the gates the comment relies on can be set: no deployment-branch policy, no required reviewers, and no main-branch protection. The trust policy then reduces to "any job in this repo that says `environment: production`". Two concrete paths:
1. `gh workflow run deploy.yaml --ref some-branch` (line 10 has no branch restriction) deploys that branch's backend, frontend and `deploy/` scripts to prod.
2. A pushed branch that adds any workflow with `environment: production` can mint the role and run `ssm send-command` as root on the box. The README's "optionally add a required reviewer" step can't be done.

Today you're the only collaborator (`gh api .../collaborators` → `SpencerPresley`), so the realistic actor is a leaked token or an agent session pushing a branch, not a stranger.

**Options:**
- **(a) Drop `environment:` and pin `sub` to `<immutable-prefix>:ref:refs/heads/main`.** That is the default subject for a non-environment job on `push`/`workflow_dispatch` from main.
  - Pros: works on Free; a branch push or a dispatch from another branch can no longer assume the role; no cost.
  - Cons: diverges from the decisions doc's `environment:production` pin; anyone who can push to main still deploys, since main can't be protected on Free; GitHub's deployment history UI is lost.
- **(b) Keep `environment:` and customize the sub template to also include `ref`** (`PUT /repos/{owner}/{repo}/actions/oidc/customization/sub`).
  - Pros: keeps the doc's pin and adds the branch check.
  - Cons: I haven't verified how customization combines with immutable subjects, so it needs the dry-run token decode from B1; more moving parts.
- **(c) Upgrade to GitHub Pro.** That enables environments on private repos (per the docs page above). I haven't verified whether required reviewers specifically are available on Pro for private repos.
  - Pros: the design works as written.
  - Cons: it costs money, so it's your call.

**Recommendation:** (a). It's the only free option whose behavior is fully documented, and it closes the any-branch path. Whichever you pick, rewrite the `github.tf:23-25` comment and the README so they stop promising protection that doesn't exist.

### S2. AWS credentials are in the environment while untrusted dependency code runs
`.github/workflows/deploy.yaml:44-91`

**Evidence:** at the pinned SHA, `configure-aws-credentials` `action.yml:76` exports env credentials by default unless `aws-profile` is set (it isn't). Steps that run after it:
- `docker build` (line 63)
- `npm ci` (line 89). `frontend/package-lock.json` has 2 `"hasInstallScript": true` packages.
- `npm run build` → `tsc -b && vite build`, which executes every Vite plugin.

**Failure:** a compromised npm dependency's postinstall script, or a malicious Vite plugin release, reads `AWS_ACCESS_KEY_ID/SECRET/SESSION_TOKEN` from its environment, which are valid for 1 hour. With them it can run `aws ssm send-command --document-name AWS-RunShellScript --instance-ids i-...` and get root on prod. From there it has every SecureString via the instance role, the documents bucket and the DB. This is the highest-value credential in the system sitting next to the largest third-party code surface.

**Fix:**
- Reorder the steps: checkout → setup-node → `npm ci` → `npm run build` → `docker build` → collectstatic → **then** `configure-aws-credentials` → ECR login → push → SSM deploy → sync → invalidate. The ECR "already exists" check moves after the build, so a re-run rebuilds; it can't re-push because tags are IMMUTABLE, so skip the push if `describe-images` hits.
- Better still, split the build into its own job without `id-token: write`, pass `dist/` and the image tarball to the deploy job as artifacts, and give only the deploy job the role.
- Residual risk with reordering alone: `id-token: write` is job-scoped, so any step in the job can request its own token. Only the job split removes that.

### S3. The real Anthropic key does end up in Terraform state
`infra/main/config.tf:70-80`, `infra/README.md:62-63`

**Evidence:** `aws_ssm_parameter` at v6.70.0 (`internal/service/ssm/parameter.go`):
- line 294 reads with `findParameterByName(ctx, conn, d.Id(), true)`, i.e. `WithDecryption: true` (line 468);
- line 355 does `d.Set(names.AttrValue, param.Value)` unless the resource uses `value_wo` (lines 347-349).

`ignore_changes = [value]` only suppresses the diff. It doesn't stop refresh from writing the value.

**Failure:** you `put-parameter` the real key, then the next `terraform plan` refreshes, and `s3://clearpath-tfstate-381491937698/main/terraform.tfstate` now holds the decrypted Anthropic key. The README's "the real key never enters Terraform state" is false. Impact is limited: the state bucket is private, SSE and TLS-only. But this is the one secret the author explicitly designed to keep out, and the doc tells you it worked.

**Fix:** pick one.
- Use `value_wo = "placeholder-set-out-of-band"` plus `value_wo_version = 1`. Read then sets `value` to nil. Write-only arguments need Terraform ≥ 1.11.0 (provider doc `website/docs/r/ssm_parameter.html.markdown:15` at v6.70.0, which also says write-only values "are never stored to state"), so bump `required_version` in `versions.tf:2` and `bootstrap/main.tf:6` (local is 1.16.2, so this is fine).
- Or remove the resource and document `aws ssm put-parameter` as a one-time step. `render-env.sh` already picks up any direct child of the prefix.

The same `value_wo` / `password_wo` mechanism would also keep `DJANGO_SECRET_KEY` and the RDS password out of state if you want that later. That's optional; the author's choice to leave them is a stated tradeoff.

### S4. `/django-admin/login/` has no throttling at any layer, and no MFA
`infra/main/waf.tf:57-125` (the rate rule's scope-down)

**Evidence:**
- The WAF rate rule only matches POSTs to `/_allauth/` paths containing `/v1/auth/`.
- allauth 65.20.1's `login_failed` rate limit is consumed in `DefaultAccountAdapter.pre_authenticate` (`allauth/account/adapter.py:791-800`), which only `adapter.authenticate` calls (line 808).
- `AuthenticationBackend.authenticate` (`allauth/account/auth_backends.py:21-30`) has no rate limit, and Django admin's login form calls `django.contrib.auth.authenticate` → backends directly.
- `git grep secure_admin_login` finds nothing, so allauth.mfa isn't wired into admin either.

**Failure:** `/django-admin/*` is routed publicly (edge.tf:7). An attacker can POST `username=<staff email>&password=<guess>` to `https://dxxx.cloudfront.net/django-admin/login/` with no limit at WAF, Django or allauth. A hit gives them a staff session that never had to pass TOTP. That bypasses both controls the spec relies on for login (WAF rate rule and MFA).

**Fix (infra, this PR):** turn the path half of the scope-down into an `or_statement`: (`/_allauth/` AND `/v1/auth/`) OR `STARTS_WITH /django-admin/login`. Alternatively, put `/django-admin/*` behind a WAF IP-set allow rule.

**Fix (app, follow-up):** `admin.site.login = secure_admin_login(admin.site.login)` (it exists at `allauth/account/decorators.py:90` in 65.20.1, but check how it behaves with `HEADLESS_ONLY = True`), or make the admin require an allauth-MFA'd session.

**Related app-side note:** there's no `CACHES` in settings, so allauth's rate-limit counters live in per-process LocMemCache. `--workers=2` doubles the effective limit and every deploy resets it. Point `CACHES` at the Redis you already run.

### S5. `terraform plan -out=tfplan` writes a secrets-bearing file that `.gitignore` doesn't cover
`infra/README.md:40-41`, `.gitignore:24`

**Failure:**
- `.gitignore` ignores `*.tfplan`, but the README's `-out=tfplan` file has no extension.
- Plan files contain the `random_password` results (DB password, Django secret key) in plaintext.
- Running `git add -A` from the repo root after following the runbook stages `infra/main/tfplan`, and the repo has agent sessions that commit.

**Fix:** use `-out=main.tfplan` in the README, or add `tfplan` to `.gitignore`. Both are one-line changes.

---

## Nits

- **N1. The instance role's SSM parameter scoping is cosmetic.** `app.tf:128-136` limits `GetParameter*` to `parameter/clearpath/*`, but the attached `AmazonSSMManagedInstanceCore` (I read its default version via `aws iam get-policy-version`) grants `ssm:GetParameter` and `ssm:GetParameters` on `"*"`. The account has no other parameters today (`describe-parameters` → `[]`), so there's no impact yet. Fix the comment, or accept it knowingly.
- **N2. `ec2:GetManagedPrefixListEntries` on `*`** (`app.tf:140-144`) can be scoped to `arn:aws:ec2:us-east-1:aws:prefix-list/pl-3b927c52`. Low value; the data is public.
- **N3. Containers can reach IMDS.** Hop limit 2 (`app.tf:64`) is required for the containers to use the instance role, so any SSRF in Django can reach the role's credentials (all SecureStrings, the documents bucket). IMDSv2 blunts GET-only SSRF. This is a design tradeoff, not a bug; name it in the decisions doc. The alternative, passing credentials explicitly to just the web/worker containers, costs complexity.
- **N4. No rollback path is documented.** If `up --wait` fails (`deploy.sh:32`), the new containers are left running unhealthy and prod is down. The rollback is "Re-run all jobs" on the last good workflow run: it reuses its SHA, and the image is still in ECR (20 kept), with expand-only migrations. Put that in the README.
- **N5. The SSM poll aborts on any transient API error** (`deploy.yaml:130-131`, e.g. `ThrottlingException`). The job fails while the deploy keeps running on the box. Retry a few times before `exit 1`. Otherwise status handling is complete: Pending/InProgress/Delayed loop; Success exits 0; Cancelled, TimedOut, Failed and Cancelling all exit 1 with stdout/stderr; there's a 20-minute deadline. Note that `StandardOutputContent` is truncated by the API, so a long migrate log will be cut off.
- **N6. Inline payload size.** I measured the base64 of `deploy/` at 9.8 KB (compose 3.6 KB, render-env 4.0 KB, deploy 2.1 KB). The Systems Manager quotas page (https://docs.aws.amazon.com/general/latest/gr/ssm.html) lists no SendCommand parameter-size quota, so I can't give a limit. It will be proven on the first deploy. If it ever fails with a size error, ship `deploy/` through S3.
- **N7. The trigger `paths` miss `.github/workflows/deploy.yaml`** (`deploy.yaml:6-9`). A workflow-only change doesn't deploy, which is surprising when you're fixing B1/S2.
- **N8. RDS AZ isn't pinned** (`database.tf:33-68`). The instance is in `private[0]` (`use1-az?a`), but RDS can land in either subnet, which costs cross-AZ latency and $0.01/GB each way. Fix: `availability_zone = aws_subnet.private[0].availability_zone`.
- **N9. Destroy defaults wipe everything.** `db_skip_final_snapshot = true`, `force_destroy_buckets = true` and `deletion_protection = false` mean that an accidental destroy, or any change that forces RDS replacement, drops the DB and the versioned "review evidence" bucket with no snapshot. This is documented, but I'd flip the snapshot default to `false`. A final snapshot costs pennies.
- **N10. No logs or alarms.** There are no CloudFront standard logs, WAF logging, container log shipping or alarms. Debugging a WAF false positive (the author flags `CrossSiteScripting_BODY` on marketing copy) depends on 3-hour sampled requests. At minimum, add a WAF logging configuration to a `aws-waf-logs-*` S3 bucket.
- **N11. IPv6 may weaken the per-IP rate limit (unverified).** `is_ipv6_enabled = true` (`edge.tf:107`) and the rate rule uses `aggregate_key_type = "IP"`. The WAF aggregation docs (https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-options.html) say IP aggregation uses "the IP address from the web request origin" and say nothing about grouping IPv6 by prefix. *If* it counts each full IPv6 address separately, an attacker holding one /64 can rotate addresses past the 50-per-5-minute limit. Options: disable IPv6 (US demo users won't notice), or add a second, looser rule that aggregates by ASN, which the same page documents.
- **N12. Paths without a trailing slash hit the SPA.** `/django-admin` and `/api` don't match `/django-admin/*` or `/api/*`, so they get the SPA's `index.html` instead of Django's slash redirect. Cosmetic.
- **N13. `redis:7-alpine` is a mutable tag pulled from Docker Hub** through the NAT (`compose.prod.yaml:26`). Pin it by digest, as the compose binary already is.
- **N14. Cost.** The ≈$93/mo estimate is plausible. NAT is $33 of it, and the README already names the NAT-instance alternative (~$3). No change needed for a demo.

---

## Verified OK (checked, not taken from the report)

- **Action SHAs:** checked with `gh api repos/<r>/git/ref/tags/<t>`. checkout v7.0.1 `3d3c42e…`, configure-aws-credentials v6.3.0 `e1253824…` and setup-node v7.1.0 `949feb24…` are all `commit` objects matching the workflow. The compose v5.6.1 `docker-compose-linux-x86_64` asset digest is `sha256:47737f42…`, matching `app.tf:56`.
- **Origin request policy** (`aws cloudfront list-origin-request-policies --type managed`): `Managed-AllViewerAndCloudFrontHeaders-2022-06` is `allViewerAndWhitelistCloudFront` with cookies `all`, query strings `all`, and `CloudFront-Forwarded-Proto` among its 21 CloudFront headers. So Django receives the viewer `Host` (matching `DJANGO_ALLOWED_HOSTS`), the session/CSRF cookies, `X-CSRFToken`, and the proto header that `prod.py:6` keys `SECURE_PROXY_SSL_HEADER` on. The author's reason for rejecting AllViewerExceptHostHeader is correct.
- **SPA rewrite:** it's attached only to `default_cache_behavior` (`edge.tf:143-146`). The four app path patterns are ordered behaviors with no function, so API paths are never rewritten. `/static/admin/*` keeps its file extensions and passes through.
- **VPC origin wiring** (checked against the AWS VPC-origins page): IGW present; private subnet; use1-az3 excluded by zone ID; SG Option 1 (`com.amazonaws.global.cloudfront.origin-facing`) is documented as valid before the VPC origin exists; the EC2 origin domain is the private IP DNS name. No public IP, no key pair, no port 22, IMDSv2 required, encrypted root volume.
- **uvicorn 0.54.0 proxy headers** (`uvicorn/middleware/proxy_headers.py:109,136,180`): `*` short-circuits to always-trust, CIDRs are parsed with `ip_network`, and XFF is walked `reversed`. The `--forwarded-allow-ips` reasoning holds. allauth 65.20.1 `get_client_ip` falls back to `REMOTE_ADDR` when `TRUSTED_PROXY_COUNT` is 0 (`allauth/core/internal/httpkit.py:198-221`).
- **RDS:** private, SG ingress only from the app SG on 5432, encrypted, PG 17. The default SG is emptied.
- **Buckets:** frontend is OAC-only, keyed on the distribution ARN; documents is versioned, SSE, public access blocked and TLS-only; the app role has `DeleteObject` but not `DeleteObjectVersion`, so deletes are recoverable.
- **Deploy role scope:** SendCommand is pinned to `document/AWS-RunShellScript` plus instances tagged `DeployTarget=clearpath-app`; ECR push is limited to the one repo; S3 to the frontend bucket; invalidation to the one distribution; no access to state or documents. `aud` is `StringEquals sts.amazonaws.com`.
- **Workflow:** `if: vars.DEPLOY_ROLE_ARN != ''` at job level skips cleanly while unset. `persist-credentials: false`; `id-token: write` only on the deploy job; concurrency group with no cancel.
- **Deploy scripts:** `render-env.sh` writes atomically (mktemp in the same directory, chmod 600, mv), rejects quotes and newlines, and fails on an empty parameter set or prefix list. `deploy.sh` is `set -euo pipefail`, migrates before `up`, waits on health checks, then requires `database == true`. Nothing in the SSM output echoes secret values.
- **Validation:** `terraform validate` on `infra/main` passes with Terraform 1.16.2 in a temporary `git archive` checkout (`init -backend=false`). I didn't run plan or apply.

## What you can settle faster than I can

1. The decoded `sub` from a dry-run token (B1, and S1 option b). Only a workflow run in this repo can produce it.
2. Whether you want option (a) or (c) for S1. Option (c) costs money.
