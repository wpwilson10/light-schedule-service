locals {
  lambda_runtime      = "python3.13"
  lambda_architecture = ["arm64"]
  lambda_handler      = "lambda_function.lambda_handler" # https://docs.aws.amazon.com/lambda/latest/dg/python-handler.html

  lights_config_s3_key_name = "configuration.json"
}
