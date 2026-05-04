variable "project_name" {
  type        = string
  description = "Project name used in dashboard and metric names."
}

variable "aws_region" {
  type        = string
  description = "AWS region."
}

variable "instance_id" {
  type        = string
  description = "EC2 instance ID to monitor."
}

variable "vpc_id" {
  type        = string
  description = "VPC ID shown on the compliance dashboard."
}

variable "vpc_flow_log_group_name" {
  type        = string
  description = "CloudWatch log group containing VPC Flow Logs."
}

variable "guardduty_detector_id" {
  type        = string
  description = "GuardDuty detector ID shown on the dashboard."
}

variable "alarm_actions" {
  type        = list(string)
  description = "Optional SNS topic ARNs or action ARNs for CloudWatch alarms."
  default     = []
}
