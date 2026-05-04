provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = var.project_name
      ManagedBy   = "terraform"
      Environment = "dark-factory-mvp"
      Owner       = var.project_name
      TTL         = "manual-destroy"
    }
  }
}
