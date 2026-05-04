output "detector_id" {
  value       = aws_guardduty_detector.this.id
  description = "GuardDuty detector ID."
}

output "detector_arn" {
  value       = aws_guardduty_detector.this.arn
  description = "GuardDuty detector ARN."
}
