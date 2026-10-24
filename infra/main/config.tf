# Runtime configuration for the app, rendered into /srv/clearpath/.env by
# deploy/render-env.sh on every deploy. Direct children of the prefix become
# env vars; /deploy/* holds inputs for render-env.sh itself.
#
# Secret values (random_password results) are stored in Terraform state, which
# is why the state bucket is private, encrypted and TLS-only.

locals {
  ssm_prefix = "/clearpath/${var.environment}"

  public_hosts = compact([
    aws_cloudfront_distribution.main.domain_name,
    var.attach_custom_domain ? var.custom_domain : "",
  ])
  primary_host = var.attach_custom_domain ? var.custom_domain : aws_cloudfront_distribution.main.domain_name

  app_config = {
    # localhost: the compose healthcheck calls the app from inside the container.
    DJANGO_ALLOWED_HOSTS        = join(",", concat(local.public_hosts, ["localhost"]))
    DJANGO_CSRF_TRUSTED_ORIGINS = join(",", [for h in local.public_hosts : "https://${h}"])
    FRONTEND_BASE_URL           = "https://${local.primary_host}"
    POSTGRES_HOST               = aws_db_instance.main.address
    POSTGRES_PORT               = tostring(aws_db_instance.main.port)
    POSTGRES_DB                 = aws_db_instance.main.db_name
    POSTGRES_USER               = aws_db_instance.main.username
    DOCUMENTS_BUCKET            = aws_s3_bucket.documents.bucket
    AWS_DEFAULT_REGION          = var.region
  }

  deploy_config = {
    VPC_CIDR                  = aws_vpc.main.cidr_block
    CLOUDFRONT_PREFIX_LIST_ID = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id
  }
}

resource "aws_ssm_parameter" "app_config" {
  for_each = local.app_config

  name  = "${local.ssm_prefix}/${each.key}"
  type  = "String"
  value = each.value
}

resource "aws_ssm_parameter" "deploy_config" {
  for_each = local.deploy_config

  name  = "${local.ssm_prefix}/deploy/${each.key}"
  type  = "String"
  value = each.value
}

resource "random_password" "django_secret_key" {
  length           = 64
  special          = true
  override_special = "-_.!*~+="
}

resource "aws_ssm_parameter" "django_secret_key" {
  name  = "${local.ssm_prefix}/DJANGO_SECRET_KEY"
  type  = "SecureString"
  value = random_password.django_secret_key.result
}

resource "aws_ssm_parameter" "postgres_password" {
  name  = "${local.ssm_prefix}/POSTGRES_PASSWORD"
  type  = "SecureString"
  value = random_password.db.result
}

# The real key is set by hand (see infra/README.md) and never enters
# Terraform; ignore_changes keeps apply from resetting it to the placeholder.
resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "${local.ssm_prefix}/ANTHROPIC_API_KEY"
  type  = "SecureString"
  value = "placeholder-set-out-of-band"

  lifecycle {
    ignore_changes = [value]
  }
}
