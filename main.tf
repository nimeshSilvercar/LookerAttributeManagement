provider "aws" {
  region = "${var.aws_region}"
}

data "archive_file" "lambda_placeholder" {
  count       = "${var.create_empty_function ? 1 : 0}"
  type        = "zip"
  output_path = "${path.module}/${var.deployment_package_file_name}"

  source_dir  = "${path.module}/placeholders"
}

data "aws_iam_policy_document" "policy" {
  statement {
    sid     = ""
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      identifiers = ["lambda.amazonaws.com"]
      type        = "Service"
    }
  }
//  statement {
//    sid     = ""
//    effect  = "Allow"
//    actions = ["sts:AssumeRole"]
//
//    principals {
//      identifiers = ["sns.amazonaws.com"]
//      type = "Service"
//    }
//  }
}

resource "aws_s3_bucket_object" "zip_file_upload" {
  bucket  = "${var.deployment_bucket_name}"
  key     = "${var.deployment_package_file_name}"
  source  = "${path.module}/${var.deployment_package_file_name}"
}

resource "aws_s3_bucket" "deployment_package_source" {
  bucket  = "${var.deployment_bucket_name}"
  acl     = "private"
  policy  = ""
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }

  tags = {
    name        = "OEM Attributes Package Source Bucket"
    project     = "Looker Insights Automation"
    environment = "Dev"
  }
}

resource "aws_lambda_permission" "cloudwatch_invoke" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = "${aws_lambda_function.manage_group_attributes.function_name}"
  principal     = "events.amazonaws.com"
  source_arn    = "${aws_cloudwatch_event_rule.daily_trigger.arn}"
}

resource "aws_iam_role" "lambda" {
  name               = "${var.function_name}_lambda_role"
  assume_role_policy = "${data.aws_iam_policy_document.policy.json}"
}

//resource "aws_sns_topic" "manage_attributes_dead_letter" {
//  name = "ManageAttributesLambdaDeadLetter"
//  display_name = "OEM Fail"
//
//  tags = {
//    name        = "OEM Attribute Updates Function"
//    project     = "Looker Insights Automation"
//    environment = "Dev"
//  }
//}

resource "aws_lambda_function" "manage_group_attributes" {
  function_name = "${var.function_name}"
  description   = "Function that handles updates and additions to Groups and User Attributes in Looker."
  s3_bucket     = "${aws_s3_bucket.deployment_package_source.bucket}"
  s3_key        = "${var.deployment_package_file_name}"

  role          = "${aws_iam_role.lambda.arn}"
  handler       = "run_oem_attribute_updates.lambda_handler"
  runtime       = "python3.6"
  timeout       = 120

//  dead_letter_config {
//    target_arn = "${aws_sns_topic.manage_attributes_dead_letter.arn}"
//  }

  tags = {
    name        = "OEM Attribute Updates Function"
    project     = "Looker Insights Automation"
    environment = "Dev"
  }
}

resource "aws_cloudwatch_event_rule" "daily_trigger" {
  name                = "daily-oem-attributes-check"
  description         = "Daily rule checked at midnight with Lambda function target."
  schedule_expression = "cron(0 0 * * ? *)"
  is_enabled          = "true"

  tags = {
    name        = "OEM Lambda Function Daily Trigger"
    project     = "Looker Insights Automation"
    environment = "Dev"
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = "${aws_cloudwatch_event_rule.daily_trigger.name}"
  target_id = "manage_group_attributes"
  arn       = "${aws_lambda_function.manage_group_attributes.arn}"
}
