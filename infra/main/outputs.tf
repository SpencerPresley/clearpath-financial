output "cloudfront_domain" {
  value = aws_cloudfront_distribution.main.domain_name
}

output "cloudfront_distribution_id" {
  description = "GitHub repo variable CLOUDFRONT_DISTRIBUTION_ID"
  value       = aws_cloudfront_distribution.main.id
}

output "ecr_repository_url" {
  description = "GitHub repo variable ECR_REPOSITORY_URL"
  value       = aws_ecr_repository.backend.repository_url
}

output "deploy_role_arn" {
  description = "GitHub repo variable DEPLOY_ROLE_ARN (deploys are skipped while it's unset)"
  value       = aws_iam_role.deploy.arn
}

output "app_instance_id" {
  description = "GitHub repo variable APP_INSTANCE_ID"
  value       = aws_instance.app.id
}

output "frontend_bucket" {
  description = "GitHub repo variable FRONTEND_BUCKET"
  value       = aws_s3_bucket.frontend.bucket
}

output "documents_bucket" {
  value = aws_s3_bucket.documents.bucket
}

output "rds_endpoint" {
  value = aws_db_instance.main.endpoint
}

# Add at Squarespace by hand. Squarespace wants the host part only, without
# the trailing ".spencerpresley.com.".
output "custom_domain_validation_records" {
  description = "ACM DNS-validation CNAME(s); empty unless custom_domain is set"
  value = local.custom_domain_enabled ? [
    for o in aws_acm_certificate.custom[0].domain_validation_options : {
      type  = o.resource_record_type
      name  = o.resource_record_name
      value = o.resource_record_value
    }
  ] : []
}

output "custom_domain_cname" {
  description = "CNAME pointing the custom domain at CloudFront; add after attach_custom_domain = true"
  value = var.attach_custom_domain ? {
    type  = "CNAME"
    name  = var.custom_domain
    value = aws_cloudfront_distribution.main.domain_name
  } : null
}
