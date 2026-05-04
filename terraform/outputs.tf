output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "instance_id" {
  value = aws_instance.provisioner.id
}

output "public_ip" {
  value = aws_instance.provisioner.public_ip
}

output "private_key_path" {
  value     = local_sensitive_file.operator_private_key.filename
  sensitive = true
}

output "ssm_start_session" {
  value = "aws ssm start-session --target ${aws_instance.provisioner.id} --region ${var.aws_region} --profile ${var.aws_profile}"
}

output "bootstrap_log_command" {
  value = "aws ssm start-session --target ${aws_instance.provisioner.id} --region ${var.aws_region} --profile ${var.aws_profile} --document-name AWS-StartInteractiveCommand --parameters command='sudo tail -n 200 /var/log/zt-bootstrap.log'"
}

output "verify_log_command" {
  value = "aws ssm start-session --target ${aws_instance.provisioner.id} --region ${var.aws_region} --profile ${var.aws_profile} --document-name AWS-StartInteractiveCommand --parameters command='sudo cat /var/log/zt-verify.json'"
}

output "guardduty_detector_id" {
  value = module.guardduty.detector_id
}

output "cloudwatch_dashboard_name" {
  value = module.cloudwatch.dashboard_name
}

output "cloudwatch_metric_namespace" {
  value = module.cloudwatch.metric_namespace
}

output "cloudwatch_dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${module.cloudwatch.dashboard_name}"
}

output "agent_audit_kms_key_arn" {
  value = aws_kms_key.audit_signing.arn
}

output "agent_audit_log_group_name" {
  value = aws_cloudwatch_log_group.agent_audit.name
}
