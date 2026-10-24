# Infrastructure (AWS, Terraform)

Account `381491937698`, region `us-east-1`, AWS CLI profile `clearpath`. Both stacks hardcode the
profile and refuse other accounts (`allowed_account_ids`). Architecture and rationale: `docs/decisions.md`
→ "Hosting (AWS, Terraform)".

```
bootstrap/   S3 bucket for the main stack's state (local state, applied once)
main/        everything else: VPC, EC2, RDS, S3, ECR, CloudFront + VPC origin, WAF, SSM params, GitHub OIDC
../deploy/   compose.prod.yaml, render-env.sh, deploy.sh: run on the server by the deploy workflow
```

```
viewer ─▶ CloudFront (WAF, geo=US) ─┬─ default ─────────────────▶ S3 frontend (OAC)  [SPA rewrite fn]
                                    └─ /api /_allauth /accounts /django-admin
                                          ─▶ VPC origin ─▶ EC2 :8000 (private subnet, compose: web/worker/beat/redis)
                                                              ├─▶ RDS Postgres 17 (private)
                                                              └─▶ NAT ─▶ ECR, SSM, Anthropic API
```

## Bootstrap (once; already done)

```sh
cd infra/bootstrap
terraform init && terraform apply
```

Creates `clearpath-tfstate-381491937698` (versioned, SSE-S3, public access blocked, TLS-only,
`prevent_destroy`). Its own state is local and gitignored; if lost, `terraform import
aws_s3_bucket.state clearpath-tfstate-381491937698` (and the sub-resources) re-adopts it.

The main stack locks state with S3-native lockfiles (`use_lockfile = true`, a `.tflock` object next to
the state); DynamoDB locking is deprecated in the S3 backend.

## Plan / apply

```sh
cd infra/main
terraform init
terraform plan -out=main.tfplan   # *.tfplan is gitignored; plan files hold secrets in plaintext
terraform apply main.tfplan
```

First apply takes ~20–25 min, mostly the CloudFront VPC origin (up to 15 min to deploy) and the
distribution. Then set the GitHub repo **variables** (not secrets; nothing here is secret) from the
outputs:

```sh
gh variable set DEPLOY_ROLE_ARN            --body "$(terraform output -raw deploy_role_arn)"
gh variable set ECR_REPOSITORY_URL         --body "$(terraform output -raw ecr_repository_url)"
gh variable set APP_INSTANCE_ID            --body "$(terraform output -raw app_instance_id)"
gh variable set FRONTEND_BUCKET            --body "$(terraform output -raw frontend_bucket)"
gh variable set CLOUDFRONT_DISTRIBUTION_ID --body "$(terraform output -raw cloudfront_distribution_id)"
```

Until `DEPLOY_ROLE_ARN` is set, the deploy workflow skips its jobs instead of failing.

**What gates a deploy.** The deploy role trusts only OIDC tokens whose `sub` is
`repo:SpencerPresley@153392395/clearpath-financial@1431827457:ref:refs/heads/main`. That's the
immutable subject format GitHub uses for repos created after July 2026; the value was confirmed by
decoding a real token from this repo. So only workflow runs on `main` can deploy. That covers pushes
and `workflow_dispatch` from main, and the workflow also skips itself on any other ref. There is **no**
GitHub environment, required reviewer or branch protection behind it: on the Free plan a private repo
gets none of those. Anyone who can push to `main` can deploy. If the repo moves to a paid plan, the
`environment:` + required-reviewer route becomes available.

The workflow has two build jobs that run all third-party code (npm, Vite, uv, Docker) without any
`id-token` permission. A separate `deploy` job, the only one that can mint AWS credentials, runs only
our checked-in scripts and the AWS CLI.

## Set the Anthropic API key

Terraform creates `/clearpath/prod/ANTHROPIC_API_KEY` with a placeholder through the write-only
`value_wo` argument (Terraform ≥ 1.11). Terraform never stores that value or reads it back, so the real
key you set by hand doesn't land in state on later refreshes. Don't bump `value_wo_version` in
`main/config.tf`: that would overwrite the real key with the placeholder. Set the real key once with:

```sh
read -rs KEY   # paste, Enter
aws ssm put-parameter --profile clearpath --region us-east-1 \
  --name /clearpath/prod/ANTHROPIC_API_KEY --type SecureString --overwrite --value "$KEY"
unset KEY
```

It takes effect on the next deploy (render-env.sh re-reads SSM). To apply it without a code change,
run the Deploy workflow manually from main (`gh workflow run deploy.yaml --ref main`).

## Rollback

`deploy.sh` stops with the new containers in place if `up --wait` or the health check fails, so prod
stays down until you act. Migrations run first and aren't reversed, which is why they must be
expand-only (backward-compatible with the previous release).

- **Preferred:** in GitHub Actions, open the last good Deploy run and click *Re-run all jobs*. It
  rebuilds that commit, reuses its image (still in ECR, which keeps the last 20), and redeploys that
  commit's `deploy/` scripts and frontend. Use *all* jobs, not just failed ones: build artifacts are
  kept for 1 day.
- **From a shell:** start a session (see Shell access), then run
  `sudo /srv/clearpath/deploy.sh <ecr_repository_url>:<good-sha>`. This only rolls back the backend
  image; the frontend stays on whatever was last synced.

## Runtime configuration

Every direct child of `/clearpath/prod/` becomes a line in `/srv/clearpath/.env` on each deploy:
secrets (`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `ANTHROPIC_API_KEY`) and plain config Terraform
derives (`POSTGRES_HOST`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `FRONTEND_BASE_URL`,
`DOCUMENTS_BUCKET`, ...). To add a setting, add it to `local.app_config` in `main/config.tf` (or
`put-parameter` by hand for secrets) and redeploy.

## Shell access

No SSH, no port 22. Use Session Manager (needs the
[session-manager-plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)):

```sh
aws ssm start-session --profile clearpath --region us-east-1 --target "$(terraform output -raw app_instance_id)"
sudo -i; cd /srv/clearpath; docker compose -f compose.prod.yaml ps
```

## Custom domain (`clearpath.spencerpresley.com`)

DNS is at Squarespace, so validation is manual and takes two applies:

1. `terraform apply -var custom_domain=clearpath.spencerpresley.com`, then add the
   `custom_domain_validation_records` output as a CNAME in Squarespace. Wait for the ACM certificate
   to show *Issued*.
2. `terraform apply -var custom_domain=clearpath.spencerpresley.com -var attach_custom_domain=true`,
   then add the `custom_domain_cname` output (`clearpath` → `dxxxx.cloudfront.net`) in Squarespace.
   This also updates `DJANGO_ALLOWED_HOSTS` / CSRF origins / `FRONTEND_BASE_URL`; redeploy to pick
   them up.

Put both variables in a `terraform.tfvars` once settled so later applies don't drop them.

## Destroy

```sh
cd infra/main && terraform destroy
```

With the defaults, destroy removes everything, including the contents of the frontend, documents and
WAF-log buckets and the ECR images (`force_destroy_buckets = true`). RDS deletion protection is off,
but the database leaves a final snapshot named `clearpath-prod-final` (`db_skip_final_snapshot =
false`). That snapshot outlives the stack and costs storage until you delete it. A second destroy
fails while a snapshot of that name exists: delete it first (`aws rds delete-db-snapshot
--db-snapshot-identifier clearpath-prod-final`), or pass `-var db_skip_final_snapshot=true`. The
state bucket survives (`prevent_destroy`); to remove it, delete that lifecycle block and destroy
`bootstrap/`.

## Logs

WAF request logs (every request, with `Cookie`, `Authorization`, `X-CSRFToken` and `X-Session-Token`
redacted) go to `s3://aws-waf-logs-clearpath-381491937698/AWSLogs/…`. They arrive in 5-minute files
and are kept 14 days (`waf_log_retention_days`). Container logs live on the box only
(`docker compose -f compose.prod.yaml logs`, json-file driver, 5 × 20 MB per container).

## Estimated monthly cost (us-east-1, always on, light traffic)

Unit prices from the AWS Price List API (`aws pricing get-products`, queried 2026-10-24) unless marked.
730 hours/month.

| Component | Basis | $/month |
|---|---|---|
| NAT gateway | $0.045/h + $0.045/GB processed (~5 GB of image pulls/API calls) | 33.10 |
| EC2 t3.medium | $0.0416/h | 30.37 |
| RDS db.t4g.micro, Single-AZ | $0.016/h | 11.68 |
| WAF | $5/web ACL (AWS WAF pricing page, *not* from the API) + 4 rules × $1 + $0.60/M requests | ~9.00 |
| Public IPv4 (NAT's EIP) | $0.005/h | 3.65 |
| EBS gp3 root, 30 GB | $0.08/GB-mo | 2.40 |
| RDS gp3 storage, 20 GB | $0.115/GB-mo; backups free up to DB size | 2.30 |
| ECR | ~20 images × ~0.2 GB at $0.10/GB-mo (*estimate*) | ~0.40 |
| CloudFront, CloudFront Functions, S3, SSM (standard params), WAF logs to S3 (vended-log delivery charge on a few MB/month) | inside free tiers / pennies at this traffic (*estimate*) | ~0.50 |
| CloudFront VPC origin | no additional charge (AWS) | 0 |
| **Total** | | **≈ $93** |

The NAT gateway is the largest line and is pure fixed cost. Cheaper options if this outlives the demo:
VPC endpoints don't help (interface endpoints are ~$7.30/mo per endpoint per AZ, *estimate*, and we'd need ECR api+dkr, SSM ×3, S3
gateway, plus egress to Anthropic still needs NAT); a NAT instance (t4g.nano, ~$3/mo) would.
Stopping the EC2 and RDS instances when idle saves ~$42/mo; RDS auto-restarts after 7 days stopped.
