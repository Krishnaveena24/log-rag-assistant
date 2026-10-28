output "function_name" {
  value = aws_lambda_function.assistant.function_name
}

output "log_bucket" {
  value = aws_s3_bucket.logs.id
}
