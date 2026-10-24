locals {
  # The deploy role may only SendCommand to instances carrying this tag.
  deploy_tag_key   = "DeployTarget"
  deploy_tag_value = "clearpath-app"
  app_port         = 8000
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# Same list the CloudFront VPC origin docs say to allow on the origin's SG.
data "aws_ec2_managed_prefix_list" "cloudfront_origin_facing" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "App server: port ${local.app_port} from CloudFront only"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${local.name}-app" }
}

# Option 1 in the VPC-origin docs. Option 2 (the service-managed
# CloudFront-VPCOrigins-Service-SG) is tighter but only exists after the VPC
# origin is created, which would make the first apply two-phase.
# The prefix list (49 entries today) counts against the 60-rules-per-SG quota.
resource "aws_vpc_security_group_ingress_rule" "app_from_cloudfront" {
  security_group_id = aws_security_group.app.id
  description       = "CloudFront VPC origin"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id
  ip_protocol       = "tcp"
  from_port         = local.app_port
  to_port           = local.app_port
}

# Egress goes through the NAT: image pulls, SSM, Anthropic API, S3, RDS.
resource "aws_vpc_security_group_egress_rule" "app_all" {
  security_group_id = aws_security_group.app.id
  description       = "All egress"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_instance" "app" {
  ami                         = data.aws_ssm_parameter.al2023_ami.insecure_value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.app.name
  associate_public_ip_address = false

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    compose_version = "v5.6.1"
    compose_sha256  = "47737f4236e6d3ccea7291995203f8f018058783b4c3a9469119811a0b5db8c0"
  })

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
    # 2, not 1: containers on the Docker bridge are one extra hop away and
    # need IMDS for instance-role credentials (S3 presigning, boto3).
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name                   = "${local.name}-app"
    (local.deploy_tag_key) = local.deploy_tag_value
  }

  lifecycle {
    # A new AL2023 release shouldn't silently replace the running server
    # (and its VPC origin). Replace deliberately with -replace.
    ignore_changes = [ami, user_data]
  }
}

# --- Instance role ---

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# SSM agent registration: Session Manager shell and Run Command deploys.
resource "aws_iam_role_policy_attachment" "app_ssm_core" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "app" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.backend.arn]
  }

  # SecureStrings use the AWS-managed aws/ssm key, whose key policy already
  # allows in-account callers via SSM, so no kms:Decrypt grant is needed.
  statement {
    sid = "ReadConfig"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]
    resources = ["arn:aws:ssm:${var.region}:${var.account_id}:parameter/clearpath/*"]
  }

  # render-env.sh reads the live CloudFront ranges to build uvicorn's
  # --forwarded-allow-ips. Public, read-only data.
  statement {
    sid       = "ReadCloudFrontPrefixList"
    actions   = ["ec2:GetManagedPrefixListEntries"]
    resources = ["*"]
  }

  statement {
    sid       = "DocumentsList"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.documents.arn]
  }

  statement {
    sid = "DocumentsReadWrite"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.documents.arn}/*"]
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "app"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.name
}
