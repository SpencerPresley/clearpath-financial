locals {
  s3_origin_id  = "frontend-s3"
  app_origin_id = "app-ec2"

  # Everything Django serves. Same-origin with the SPA, so session cookies and
  # CSRF work without CORS.
  app_path_patterns = ["/api/*", "/_allauth/*", "/accounts/*", "/django-admin/*"]

  custom_domain_enabled = var.custom_domain != ""
}

# --- Managed policies (looked up by name so IDs aren't hand-copied) ---

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

# Forwards every viewer header *including Host*, plus CloudFront-Forwarded-Proto
# (prod.py's SECURE_PROXY_SSL_HEADER) and CloudFront-Viewer-Address.
# Chosen over AllViewerExceptHostHeader: that one rewrites Host to the origin
# domain (the instance's ip-10-...ec2.internal name), so Django would build
# URLs and CSRF Origin checks against a private hostname.
data "aws_cloudfront_origin_request_policy" "all_viewer_and_cloudfront" {
  name = "Managed-AllViewerAndCloudFrontHeaders-2022-06"
}

# HSTS, nosniff, frame and referrer headers for the SPA. Django sets its own
# on the API behaviors.
data "aws_cloudfront_response_headers_policy" "security_headers" {
  name = "Managed-SecurityHeadersPolicy"
}

# --- Origins ---

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.name}-frontend"
  description                       = "SPA bucket, CloudFront-only access"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Takes up to ~15 minutes to deploy. CloudFront creates a service-managed ENI
# in the instance's subnet; TLS terminates at the edge, and the hop to the
# instance stays on the AWS network over plain HTTP.
resource "aws_cloudfront_vpc_origin" "app" {
  vpc_origin_endpoint_config {
    name                   = "${local.name}-app"
    arn                    = aws_instance.app.arn
    http_port              = local.app_port
    https_port             = 443
    origin_protocol_policy = "http-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }

  # Provider default is 15m, the same as AWS's "up to 15 minutes"; leave headroom
  # so a slow deployment doesn't fail the apply with the origin half-created.
  timeouts {
    create = "30m"
    update = "30m"
    delete = "30m"
  }
}

resource "aws_cloudfront_function" "spa_rewrite" {
  name    = "${local.name}-spa-rewrite"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite extensionless SPA routes to /index.html"
  publish = true
  code    = file("${path.module}/functions/spa-rewrite.js")
}

# --- Optional custom domain (see variables.tf for the two-phase flow) ---

resource "aws_acm_certificate" "custom" {
  count = local.custom_domain_enabled ? 1 : 0

  domain_name       = var.custom_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# No validation_record_fqdns: DNS is at Squarespace, so this just waits for
# ACM to report ISSUED after the CNAME has been added by hand.
resource "aws_acm_certificate_validation" "custom" {
  count = var.attach_custom_domain ? 1 : 0

  certificate_arn = aws_acm_certificate.custom[0].arn
}

# --- Distribution ---

resource "aws_cloudfront_distribution" "main" {
  enabled = true
  comment = local.name
  # IPv4 only: the WAF rate rule aggregates per IP, and an IPv6 client can
  # rotate through a whole /64, so per-address limits would be easy to evade.
  # US users lose nothing by being served over IPv4.
  is_ipv6_enabled     = false
  http_version        = "http2and3"
  price_class         = "PriceClass_100" # US/Canada/Europe edges; users are US-only
  default_root_object = "index.html"
  web_acl_id          = aws_wafv2_web_acl.edge.arn
  aliases             = var.attach_custom_domain ? [var.custom_domain] : []

  origin {
    origin_id                = local.s3_origin_id
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    origin_id = local.app_origin_id
    # For EC2 VPC origins the docs say to use the instance's private IP DNS name.
    domain_name = aws_instance.app.private_dns

    vpc_origin_config {
      vpc_origin_id = aws_cloudfront_vpc_origin.app.id
      # 60s is the default-quota max; SSE assistant streams must send
      # data (or keepalives) more often than this.
      origin_read_timeout      = 60
      origin_keepalive_timeout = 5
    }
  }

  default_cache_behavior {
    target_origin_id           = local.s3_origin_id
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD", "OPTIONS"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = data.aws_cloudfront_response_headers_policy.security_headers.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_rewrite.arn
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = local.app_path_patterns
    content {
      path_pattern     = ordered_cache_behavior.value
      target_origin_id = local.app_origin_id
      # https-only rather than redirect: a redirected POST loses its body.
      viewer_protocol_policy = "https-only"
      allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
      cached_methods         = ["GET", "HEAD"]
      # CloudFront only compresses when the cache policy enables gzip/brotli,
      # and Managed-CachingDisabled doesn't, so compress = true would do nothing.
      compress                 = false
      cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
      origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_and_cloudfront.id
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "whitelist"
      locations        = ["US"]
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = !var.attach_custom_domain
    acm_certificate_arn            = var.attach_custom_domain ? aws_acm_certificate_validation.custom[0].certificate_arn : null
    ssl_support_method             = var.attach_custom_domain ? "sni-only" : null
    minimum_protocol_version       = var.attach_custom_domain ? "TLSv1.2_2021" : "TLSv1"
  }
}
