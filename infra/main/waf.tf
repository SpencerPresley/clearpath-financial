# Web ACLs for CloudFront must have scope CLOUDFRONT and live in us-east-1.

locals {
  managed_rule_groups = {
    # Cheapest block first: known-bad IPs never reach the heavier groups.
    AWSManagedRulesAmazonIpReputationList = { priority = 10, count_rules = [] }
    # SizeRestrictions_BODY blocks any body over 8 KB, which would block
    # image-mockup uploads and long content submissions; count it instead.
    AWSManagedRulesCommonRuleSet         = { priority = 30, count_rules = ["SizeRestrictions_BODY"] }
    AWSManagedRulesKnownBadInputsRuleSet = { priority = 40, count_rules = [] }
  }
}

resource "aws_wafv2_web_acl" "edge" {
  name  = "${local.name}-edge"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  dynamic "rule" {
    for_each = local.managed_rule_groups
    content {
      name     = rule.key
      priority = rule.value.priority

      override_action {
        none {}
      }

      statement {
        managed_rule_group_statement {
          vendor_name = "AWS"
          name        = rule.key

          dynamic "rule_action_override" {
            for_each = rule.value.count_rules
            content {
              name = rule_action_override.value
              action_to_use {
                count {}
              }
            }
          }
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = rule.key
        sampled_requests_enabled   = true
      }
    }
  }

  # Credential stuffing guard. Counts POSTs per IP to:
  #   - /_allauth/{browser,app}/v1/auth/... (login, 2FA authenticate, password
  #     reset, login-by-code), in front of allauth's own per-account limits;
  #   - /django-admin/login, which has no other throttle: Django admin calls
  #     the auth backends directly, bypassing allauth's rate limiting and MFA.
  # Shape is and(POST, or(...)): the provider allows only leaf statements
  # inside a scope-down's nested or, hence a regex for the allauth paths.
  rule {
    name     = "auth-post-rate-limit"
    priority = 20

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.login_rate_limit
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"

        scope_down_statement {
          and_statement {
            statement {
              byte_match_statement {
                search_string         = "POST"
                positional_constraint = "EXACTLY"
                field_to_match {
                  method {}
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
            statement {
              or_statement {
                statement {
                  regex_match_statement {
                    regex_string = "^/_allauth/[^/]+/v1/auth/"
                    field_to_match {
                      uri_path {}
                    }
                    text_transformation {
                      priority = 0
                      type     = "LOWERCASE"
                    }
                  }
                }
                statement {
                  byte_match_statement {
                    search_string         = "/django-admin/login"
                    positional_constraint = "STARTS_WITH"
                    field_to_match {
                      uri_path {}
                    }
                    text_transformation {
                      priority = 0
                      type     = "LOWERCASE"
                    }
                  }
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "auth-post-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.name}-edge"
    sampled_requests_enabled   = true
  }
}
