output "lambda_arn" {
  value = "${aws_lambda_function.manage_group_attributes.arn}"
}