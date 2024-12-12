variable "api_gateway_id" {
  description = "ID of the API Gateway created in WpwilsonSite repository"
  type        = string
}

# Uses the access credential values in the profile located at
#  "~/.aws/credentials" (Linux) or "%USERPROFILE%\.aws\credentials" (Windows).
# See https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html
variable "credentials_profile" {
  description = "Profile to use from the AWS credentials file"
  type        = string
  default     = "default"
}

variable "lights_api_route" {
  description = "API route for lights service (e.g. api_domain_prefix.domain_name.com/lights_api_route)"
  type        = string
  default     = "lights"
}

variable "lights_lambda_get_file_directory" {
  description = "Relative location of the directory containing files for lighting GET Lambda function"
  type        = string
  default     = "../aws/lights_get_lambda"
}

variable "lights_lambda_post_file_directory" {
  description = "Relative location of the directory containing files for lighting POST Lambda function"
  type        = string
  default     = "../aws/lights_post_lambda"
}

variable "project_name" {
  description = "Name for this project which will be prepended to new resources"
  type        = string
  default     = "SPA-Demo"
}

variable "region" {
  description = "AWS Region to use for this account"
  type        = string
  default     = "us-east-1"
}

