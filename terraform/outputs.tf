output "lights_config_s3_bucket_name" {
  value       = module.lights_config_s3_bucket.s3_bucket_id
  description = "Name of the S3 bucket hosting the light configuration file"
}

