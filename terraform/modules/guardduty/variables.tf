variable "project_name" {
  type        = string
  description = "Project name used for tagging."
}

variable "enabled" {
  type        = bool
  description = "Whether GuardDuty should be enabled."
  default     = true
}

variable "finding_publishing_frequency" {
  type        = string
  description = "How often GuardDuty publishes findings to EventBridge and CloudWatch Events."
  default     = "FIFTEEN_MINUTES"

  validation {
    condition     = contains(["FIFTEEN_MINUTES", "ONE_HOUR", "SIX_HOURS"], var.finding_publishing_frequency)
    error_message = "finding_publishing_frequency must be FIFTEEN_MINUTES, ONE_HOUR, or SIX_HOURS."
  }
}
