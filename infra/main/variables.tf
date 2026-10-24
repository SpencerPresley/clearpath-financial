variable "region" {
  description = "Everything lives in us-east-1: CloudFront's WAF and ACM certificates must be there anyway."
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "clearpath"
}

variable "account_id" {
  description = "The only account this stack may touch (provider allowed_account_ids)."
  type        = string
  default     = "381491937698"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "instance_type" {
  description = "x86_64 so images build natively on GitHub-hosted runners (ledger ruling)."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_gb" {
  description = "Room for a few generations of images plus Docker build cache."
  type        = number
  default     = 30
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "db_skip_final_snapshot" {
  description = "Destroy (or a forced replacement) takes a final snapshot unless this is true. A snapshot of a demo DB costs pennies."
  type        = bool
  default     = false
}

variable "force_destroy_buckets" {
  description = "Let `terraform destroy` empty the S3 buckets and ECR repo. Demo data only; set false once real documents land."
  type        = bool
  default     = true
}

# Repos created after GitHub's July 2026 cutover get an immutable OIDC subject:
# repo:OWNER@OWNER-ID/REPO@REPO-ID:... instead of repo:OWNER/REPO:....
# Source: `gh api repos/SpencerPresley/clearpath-financial/actions/oidc/customization/sub`
# (sub_claim_prefix); confirmed by decoding a real token from this repo
# (docs/plan/reports/infra-terraform.md).
variable "github_oidc_sub_prefix" {
  type    = string
  default = "repo:SpencerPresley@153392395/clearpath-financial@1431827457"
}

variable "github_deploy_ref" {
  description = "Only workflow runs on this ref may assume the deploy role."
  type        = string
  default     = "refs/heads/main"
}

variable "login_rate_limit" {
  description = "Max login-type POSTs (allauth /v1/auth/*, Django admin login) per IP per 5 minutes before WAF blocks."
  type        = number
  default     = 50
}

variable "waf_log_retention_days" {
  type    = number
  default = 14
}

# Custom domain, two phases because DNS is at Squarespace (no Route 53):
#   1. set custom_domain, apply, add the `custom_domain_validation_records`
#      output as a CNAME at Squarespace, wait for ACM to issue;
#   2. set attach_custom_domain = true, apply, add the `custom_domain_cname`
#      record. Attaching before issuance would block the apply on validation.
variable "custom_domain" {
  description = "e.g. clearpath.spencerpresley.com. Empty = use the *.cloudfront.net domain only."
  type        = string
  default     = ""
}

variable "attach_custom_domain" {
  type    = bool
  default = false

  validation {
    condition     = !var.attach_custom_domain || var.custom_domain != ""
    error_message = "attach_custom_domain requires custom_domain."
  }
}
