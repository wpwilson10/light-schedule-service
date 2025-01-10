provider "aws" {
  region  = var.region
  profile = var.credentials_profile

  default_tags {
    tags = {
      Terraform = true
      Source    = var.github_repo
    }
  }
}
