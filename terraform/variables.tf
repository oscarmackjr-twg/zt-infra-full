variable "aws_profile" {
  type        = string
  default     = "default"
  description = "Local AWS CLI profile used by Terraform."

  validation {
    condition     = var.aws_profile != ""
    error_message = "aws_profile must be set explicitly for the target AWS account."
  }
}

variable "allowed_aws_account_id" {
  type        = string
  default     = ""
  description = "Optional 12-digit AWS account ID guardrail. When set, Terraform refuses to deploy anywhere else."

  validation {
    condition     = var.allowed_aws_account_id == "" || can(regex("^[0-9]{12}$", var.allowed_aws_account_id))
    error_message = "allowed_aws_account_id must be empty or a 12-digit AWS account ID."
  }
}

variable "aws_region" {
  type        = string
  default     = "us-east-2"
  description = "AWS region for the MVP."

  validation {
    condition     = var.aws_region == "us-east-2"
    error_message = "This MVP is pinned to us-east-2."
  }
}

variable "project_name" {
  type        = string
  default     = "zt-infra-v2"
  description = "Name prefix and common tag value."

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$", var.project_name))
    error_message = "project_name must be lowercase alphanumeric/hyphen, 3-32 characters, and must not start or end with a hyphen."
  }
}

variable "instance_type" {
  type        = string
  default     = "t3.micro"
  description = "EC2 instance size."

  validation {
    condition     = contains(["t3.micro", "t3.small", "t4g.micro", "t4g.small"], var.instance_type)
    error_message = "instance_type must stay in the approved small-instance allowlist."
  }
}

variable "tailscale_secret_name" {
  type        = string
  default     = "zt-infra/tailscale-auth-key"
  description = "AWS Secrets Manager secret containing the Tailscale auth key."

  validation {
    condition     = var.tailscale_secret_name != "" && can(regex("^[A-Za-z0-9/_+=.@-]+$", var.tailscale_secret_name))
    error_message = "tailscale_secret_name must be set explicitly and contain only AWS Secrets Manager-safe path characters."
  }
}

variable "allowed_operator_cidr" {
  type        = string
  default     = "0.0.0.0/32"
  description = "Reserved for future SSH allowlist. MVP creates no public ingress."
}

variable "guardduty_enabled" {
  type        = bool
  default     = true
  description = "Enable GuardDuty in the deployment region."
}

variable "guardduty_finding_publishing_frequency" {
  type        = string
  default     = "FIFTEEN_MINUTES"
  description = "How often GuardDuty publishes findings to EventBridge and CloudWatch Events."

  validation {
    condition     = contains(["FIFTEEN_MINUTES", "ONE_HOUR", "SIX_HOURS"], var.guardduty_finding_publishing_frequency)
    error_message = "guardduty_finding_publishing_frequency must be FIFTEEN_MINUTES, ONE_HOUR, or SIX_HOURS."
  }
}

variable "cloudwatch_alarm_actions" {
  type        = list(string)
  default     = []
  description = "Optional SNS topic ARNs or CloudWatch alarm action ARNs for compliance alarms."

  validation {
    condition = alltrue([
      for action in var.cloudwatch_alarm_actions : can(regex("^arn:aws[a-zA-Z-]*:", action))
    ])
    error_message = "cloudwatch_alarm_actions must contain only AWS ARNs."
  }
}

variable "daal_enabled" {
  type        = bool
  default     = false
  description = "Enable the asynchronous DAAL/DAS blockchain attestation sidecar for zt-provisioner."
}

variable "daal_provider_mode" {
  type        = string
  default     = "cdp"
  description = "DAAL provider mode. The AWS MVP uses cdp for Coinbase Developer Platform Server Wallets."

  validation {
    condition     = contains(["cdp", "thirdweb-engine", "ethers"], var.daal_provider_mode)
    error_message = "daal_provider_mode must be cdp, thirdweb-engine, or ethers."
  }
}

variable "daal_network" {
  type        = string
  default     = "base-sepolia"
  description = "DAAL EVM network."

  validation {
    condition     = contains(["base-sepolia", "base-mainnet", "polygon-amoy"], var.daal_network)
    error_message = "daal_network must be base-sepolia, base-mainnet, or polygon-amoy."
  }
}

variable "daal_contract_address" {
  type        = string
  default     = ""
  description = "DAALog smart contract address. Required when daal_enabled is true."

  validation {
    condition     = var.daal_contract_address == "" || can(regex("^0x[0-9a-fA-F]{40}$", var.daal_contract_address))
    error_message = "daal_contract_address must be empty or a valid EVM address."
  }
}

variable "daal_batch_size" {
  type        = number
  default     = 10
  description = "Number of action hashes per DAAL batch submission."

  validation {
    condition     = var.daal_batch_size >= 1 && var.daal_batch_size <= 100
    error_message = "daal_batch_size must be between 1 and 100."
  }
}

variable "daal_secret_name" {
  type        = string
  default     = "zt-infra-v2/daal-runtime"
  description = "AWS Secrets Manager JSON secret containing DAAL runtime credentials."

  validation {
    condition     = can(regex("^zt-infra-v2/[A-Za-z0-9/_+=.@-]+$", var.daal_secret_name))
    error_message = "daal_secret_name must stay under the zt-infra-v2/ Secrets Manager namespace."
  }
}

variable "cdp_evm_account_address" {
  type        = string
  default     = ""
  description = "CDP EVM account address used by DAAL_PROVIDER_MODE=cdp."

  validation {
    condition     = var.cdp_evm_account_address == "" || can(regex("^0x[0-9a-fA-F]{40}$", var.cdp_evm_account_address))
    error_message = "cdp_evm_account_address must be empty or a valid EVM address."
  }
}
