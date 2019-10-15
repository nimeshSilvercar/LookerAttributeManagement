variable "aws_region" {
  description = "The AWS region to create things in."
  default     = "us-east-1"
}

variable "deployment_package_file_name" {
  description = "The name of the Lambda function deployment package zip file."
  default     = "run_oem_attribute_updates.zip"
}

variable "deployment_bucket_name" {
  description = "The S3 bucket that houses the deployment package."
  default     = "oem-group-attributes-metadata"
}

variable "create_empty_function" {
  description = "Enable to create empty function and empty deployment package to deploy infrastructure without code."
  default     = false
}

variable "function_name" {
  description = "The name of the Lambda function."
  default     = "run_oem_attribute_updates"
}