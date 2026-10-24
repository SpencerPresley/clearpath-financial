terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.70"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # Bucket comes from infra/bootstrap. use_lockfile is S3-native locking
  # (a .tflock object next to the state), so no DynamoDB table is needed.
  backend "s3" {
    bucket       = "clearpath-tfstate-381491937698"
    key          = "main/terraform.tfstate"
    region       = "us-east-1"
    profile      = "clearpath"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  # A repointed profile or a stray AWS_PROFILE can't apply this to another account.
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = {
      Project     = "clearpath"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
