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
terraform plan -out=tfplan
terraform apply tfplan
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

Also create the `production` environment in the repo settings (the deploy role only trusts jobs in it)
and optionally add a required reviewer. Until `DEPLOY_ROLE_ARN` is set, the deploy workflow skips its
job instead of failing.

## Set the Anthropic API key

Terraform creates `/clearpath/prod/ANTHROPIC_API_KEY` with a placeholder and ignores later value changes,
so the real key never enters Terraform state or the repo:

```sh
read -rs KEY   # paste, Enter
aws ssm put-parameter --profile clearpath --region us-east-1 \
  --name /clearpath/prod/ANTHROPIC_API_KEY --type SecureString --overwrite --value "$KEY"
unset KEY
```

It takes effect on the next deploy (render-env.sh re-reads SSM). To apply it without a code change,
run the Deploy workflow manually (`gh workflow run deploy.yaml`).

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

With the defaults (`force_destroy_buckets = true`, `db_skip_final_snapshot = true`, RDS deletion
protection off) this removes everything including bucket contents, images and the database, with no
final snapshot. Set `-var db_skip_final_snapshot=false` to keep one. The state bucket survives
(`prevent_destroy`); remove it by deleting that lifecycle block and destroying `bootstrap/`.

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
| CloudFront, CloudFront Functions, S3, SSM (standard params) | inside free tiers / pennies at this traffic (*estimate*) | ~0.50 |
| CloudFront VPC origin | no additional charge (AWS) | 0 |
| **Total** | | **≈ $93** |

The NAT gateway is the largest line and is pure fixed cost. Cheaper options if this outlives the demo:
VPC endpoints don't help (interface endpoints are ~$7.30/mo per endpoint per AZ, *estimate*, and we'd need ECR api+dkr, SSM ×3, S3
gateway, plus egress to Anthropic still needs NAT); a NAT instance (t4g.nano, ~$3/mo) would.
Stopping the EC2 and RDS instances when idle saves ~$42/mo; RDS auto-restarts after 7 days stopped.
