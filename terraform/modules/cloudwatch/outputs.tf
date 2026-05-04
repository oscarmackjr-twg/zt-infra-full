output "dashboard_name" {
  value       = aws_cloudwatch_dashboard.compliance.dashboard_name
  description = "Continuous compliance CloudWatch dashboard name."
}

output "metric_namespace" {
  value       = local.metric_namespace
  description = "Custom CloudWatch metric namespace used by compliance metrics."
}
