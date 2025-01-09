##############################################################
# S3 Bucket - Hosts lighting functionality configuration file
##############################################################

module "lights_config_s3_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "4.2.2"

  bucket_prefix = lower("${var.project_name}-lights-config-")
  force_destroy = true
}

#######################################################################
# Lambda functions - Implements light scheduling configuration updates
#######################################################################

# Function that receives HTTPS POSTS from the client website and updates the lighting schedule configuration file
module "lambda_post_function" {
  source        = "terraform-aws-modules/lambda/aws"
  version       = "7.17.0"
  handler       = local.lambda_handler
  runtime       = local.lambda_runtime
  architectures = local.lambda_architecture

  function_name                     = "${var.project_name}-Lights-Config-POST"
  description                       = "REST endpoint for updating lighting schedule configuration file."
  source_path                       = var.lambda_post_file_directory
  publish                           = true
  cloudwatch_logs_retention_in_days = 90

  # matches variables used in function code
  environment_variables = {
    CONFIG_BUCKET_NAME = module.lights_config_s3_bucket.s3_bucket_id # use the generated name with prefix
    CONFIG_KEY_NAME    = local.lights_config_s3_key_name
    SECRET_TOKEN       = var.secret_token
  }

  # allow API Gateway to call the function
  allowed_triggers = {
    APIGatewayLights = {
      service    = "apigateway"
      source_arn = "${data.aws_apigatewayv2_api.this.execution_arn}/*/*"
    }
  }

  # allow access to the config s3 bucket
  attach_policy = true
  policy        = aws_iam_policy.lambda_s3_access_policy.arn
}

# Function that receives HTTPS GETS from the client website and returns the lighting schedule configuration file
module "lambda_get_function" {
  source        = "terraform-aws-modules/lambda/aws"
  version       = "7.17.0"
  handler       = local.lambda_handler
  runtime       = local.lambda_runtime
  architectures = local.lambda_architecture

  function_name                     = "${var.project_name}-Lights-Config-GET"
  description                       = "REST endpoint for retrieving the lighting schedule configuration file."
  source_path                       = var.lambda_get_file_directory
  publish                           = true
  cloudwatch_logs_retention_in_days = 90

  # matches variables used in function code
  environment_variables = {
    CONFIG_BUCKET_NAME = module.lights_config_s3_bucket.s3_bucket_id # use the generated name with prefix
    CONFIG_KEY_NAME    = local.lights_config_s3_key_name
  }

  # allow API Gateway to call the function
  allowed_triggers = {
    APIGatewayLights = {
      service    = "apigateway"
      source_arn = "${data.aws_apigatewayv2_api.this.execution_arn}/*/*"
    }
  }

  # allow access to the config s3 bucket
  attach_policy = true
  policy        = aws_iam_policy.lambda_s3_access_policy.arn
}

##############################################################################
# IAM policy - allows Lambda functions to access the configuration S3 bucket
##############################################################################

resource "aws_iam_policy" "lambda_s3_access_policy" {
  name        = "${var.project_name}-lambda-s3-access-policy"
  description = "IAM policy allowing light scheduling Lambda functions to access the configuration S3 bucket"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid    = "AllowGetConfig",
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ],
        Resource = [
          "arn:aws:s3:::${module.lights_config_s3_bucket.s3_bucket_id}",
          "arn:aws:s3:::${module.lights_config_s3_bucket.s3_bucket_id}/*"
        ]
      },
      {
        Sid      = "AllowPutConfig",
        Effect   = "Allow",
        Action   = "s3:PutObject",
        Resource = "arn:aws:s3:::${module.lights_config_s3_bucket.s3_bucket_id}/*"
      }
    ]
  })
}

#############################################################################
# API Gateway - Imports shared gateway and adds lambda function integrations
#############################################################################

data "aws_apigatewayv2_api" "this" {
  api_id = var.api_gateway_id
}

resource "aws_apigatewayv2_integration" "get" {
  api_id                 = data.aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY" # for lambda functions
  integration_uri        = module.lambda_get_function.lambda_function_invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get" {
  api_id    = data.aws_apigatewayv2_api.this.id
  route_key = "GET /${var.api_route}"
  target    = "integrations/${aws_apigatewayv2_integration.get.id}"
}

resource "aws_apigatewayv2_integration" "post" {
  api_id                 = data.aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY" # for lambda functions
  integration_uri        = module.lambda_post_function.lambda_function_invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "post" {
  api_id    = data.aws_apigatewayv2_api.this.id
  route_key = "POST /${var.api_route}"
  target    = "integrations/${aws_apigatewayv2_integration.post.id}"
}
