data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_secretsmanager_secret" "tailscale" {
  name = var.tailscale_secret_name
}

data "aws_secretsmanager_secret_version" "tailscale_current" {
  secret_id = data.aws_secretsmanager_secret.tailscale.id
}

data "aws_secretsmanager_secret" "daal_runtime" {
  count = var.daal_enabled ? 1 : 0
  name  = var.daal_secret_name
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_partition" "current" {}

resource "tls_private_key" "operator" {
  algorithm = "ED25519"
}

resource "local_sensitive_file" "operator_private_key" {
  filename        = "${path.module}/../out/${var.project_name}.pem"
  content         = tls_private_key.operator.private_key_openssh
  file_permission = "0600"
}

resource "aws_key_pair" "operator" {
  key_name   = "${var.project_name}-operator"
  public_key = tls_private_key.operator.public_key_openssh

  tags = {
    Name = "${var.project_name}-operator"
  }
}

resource "aws_vpc" "main" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_cloudwatch_log_group" "vpc_flow_logs" {
  name              = "/aws/vpc/${var.project_name}/flow-logs"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.vpc_flow_logs.arn

  tags = {
    Name = "${var.project_name}-vpc-flow-logs"
  }
}

resource "aws_kms_key" "vpc_flow_logs" {
  description             = "Encrypt VPC Flow Logs for ${var.project_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccountAdministration"
        Effect = "Allow"
        Principal = {
          AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogsUse"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          ArnEquals = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/vpc/${var.project_name}/flow-logs"
          }
        }
      },
    ]
  })

  tags = {
    Name = "${var.project_name}-vpc-flow-logs"
  }
}

resource "aws_kms_alias" "vpc_flow_logs" {
  name          = "alias/${var.project_name}-vpc-flow-logs"
  target_key_id = aws_kms_key.vpc_flow_logs.key_id
}

resource "aws_iam_role" "vpc_flow_logs" {
  name = "${var.project_name}-vpc-flow-logs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "vpc-flow-logs.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "${var.project_name}-vpc-flow-logs-role"
  }
}

#tfsec:ignore:aws-iam-no-policy-wildcards VPC Flow Logs must create/write dynamic CloudWatch log streams under this exact log group; wildcard is scoped to the group ARN only.
resource "aws_iam_role_policy" "vpc_flow_logs" {
  name = "${var.project_name}-vpc-flow-logs-write"
  role = aws_iam_role.vpc_flow_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:PutLogEvents",
      ]
      Resource = [
        aws_cloudwatch_log_group.vpc_flow_logs.arn,
        "${aws_cloudwatch_log_group.vpc_flow_logs.arn}:*",
      ]
    }]
  })
}

resource "aws_flow_log" "vpc" {
  iam_role_arn    = aws_iam_role.vpc_flow_logs.arn
  log_destination = aws_cloudwatch_log_group.vpc_flow_logs.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-vpc-flow-log"
  }
}

resource "aws_kms_key" "audit_signing" {
  description              = "Sign zt-provisioner agent action audit records for ${var.project_name}"
  deletion_window_in_days  = 7
  enable_key_rotation      = false
  customer_master_key_spec = "ECC_NIST_P256"
  key_usage                = "SIGN_VERIFY"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccountAdministration"
        Effect = "Allow"
        Principal = {
          AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
    ]
  })

  tags = {
    Name = "${var.project_name}-audit-signing"
  }
}

resource "aws_kms_alias" "audit_signing" {
  name          = "alias/${var.project_name}-audit-signing"
  target_key_id = aws_kms_key.audit_signing.key_id
}

resource "aws_kms_key" "agent_audit_logs" {
  description             = "Encrypt zt-provisioner agent audit logs for ${var.project_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootAccountAdministration"
        Effect = "Allow"
        Principal = {
          AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogsUse"
        Effect = "Allow"
        Principal = {
          Service = "logs.${var.aws_region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          ArnEquals = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/zt/${var.project_name}/agent-audit"
          }
        }
      },
    ]
  })

  tags = {
    Name = "${var.project_name}-agent-audit-logs"
  }
}

resource "aws_kms_alias" "agent_audit_logs" {
  name          = "alias/${var.project_name}-agent-audit-logs"
  target_key_id = aws_kms_key.agent_audit_logs.key_id
}

resource "aws_cloudwatch_log_group" "agent_audit" {
  name              = "/aws/zt/${var.project_name}/agent-audit"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.agent_audit_logs.arn

  tags = {
    Name = "${var.project_name}-agent-audit"
  }
}

resource "aws_default_security_group" "locked_down" {
  vpc_id = aws_vpc.main.id

  ingress = []
  egress  = []

  tags = {
    Name = "${var.project_name}-default-deny"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.42.10.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-a"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "instance" {
  name        = "${var.project_name}-instance"
  description = "No public inbound; outbound only for SSM, package install, Tailscale."
  vpc_id      = aws_vpc.main.id

  ingress = []

  egress {
    description = "DNS UDP to VPC resolver"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  egress {
    description = "DNS TCP to VPC resolver fallback"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  #tfsec:ignore:aws-ec2-no-public-egress-sgr Intentional TCP/80 only for Ubuntu HTTP package mirrors during MVP bootstrap; no inbound rules exist.
  egress {
    description = "HTTP outbound for Ubuntu package mirrors"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  #tfsec:ignore:aws-ec2-no-public-egress-sgr Intentional TCP/443 only for AWS APIs, Tailscale control plane, npm, and vendor downloads during MVP bootstrap.
  egress {
    description = "HTTPS outbound for AWS APIs, Tailscale, npm, and downloads"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  #tfsec:ignore:aws-ec2-no-public-egress-sgr Intentional UDP/41641 only for Tailscale direct WireGuard connectivity; access remains tailnet-only.
  egress {
    description = "Tailscale direct WireGuard outbound"
    from_port   = 41641
    to_port     = 41641
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "AWS Time Sync Service"
    from_port   = 123
    to_port     = 123
    protocol    = "udp"
    cidr_blocks = ["169.254.169.123/32"]
  }

  revoke_rules_on_delete = true

  tags = {
    Name = "${var.project_name}-instance"
  }
}

resource "aws_iam_role" "instance" {
  name = "${var.project_name}-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "${var.project_name}-instance-role"
  }
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "secrets" {
  name = "${var.project_name}-read-bootstrap-secrets"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = concat(
        [data.aws_secretsmanager_secret.tailscale.arn],
        var.daal_enabled ? [data.aws_secretsmanager_secret.daal_runtime[0].arn] : []
      )
    }]
  })
}

resource "aws_iam_role_policy" "agent_audit" {
  name = "${var.project_name}-agent-audit"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SignAgentAuditRecords"
        Effect   = "Allow"
        Action   = ["kms:Sign"]
        Resource = aws_kms_key.audit_signing.arn
      },
      {
        Sid    = "WriteAgentAuditLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "${aws_cloudwatch_log_group.agent_audit.arn}:*"
      },
    ]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.project_name}-instance-profile"
  role = aws_iam_role.instance.name

  tags = {
    Name = "${var.project_name}-instance-profile"
  }
}

resource "aws_instance" "provisioner" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.instance.id]
  iam_instance_profile        = aws_iam_instance_profile.instance.name
  key_name                    = aws_key_pair.operator.key_name
  associate_public_ip_address = true

  user_data_base64 = base64gzip(templatefile("${path.module}/user-data.sh.tpl", {
    aws_region                  = var.aws_region
    project_name                = var.project_name
    tailscale_secret_name       = var.tailscale_secret_name
    tailscale_secret_version_id = data.aws_secretsmanager_secret_version.tailscale_current.version_id
    audit_kms_key_id            = aws_kms_key.audit_signing.arn
    audit_log_group_name        = aws_cloudwatch_log_group.agent_audit.name
    daal_enabled                = tostring(var.daal_enabled)
    daal_provider_mode          = var.daal_provider_mode
    daal_network                = var.daal_network
    daal_contract_address       = var.daal_contract_address
    daal_batch_size             = tostring(var.daal_batch_size)
    daal_secret_name            = var.daal_secret_name
    cdp_evm_account_address     = var.cdp_evm_account_address
    provisioner_package_json    = file("${path.module}/../provisioner/package.json")
    provisioner_actions_json    = file("${path.module}/../provisioner/policies/actions.json")
    provisioner_policy_js       = file("${path.module}/../provisioner/src/policy.js")
    provisioner_audit_js        = file("${path.module}/../provisioner/src/audit.js")
    provisioner_daal_js         = file("${path.module}/../provisioner/src/daal.js")
    provisioner_server_js       = file("${path.module}/../provisioner/src/server.js")
  }))

  user_data_replace_on_change = true

  root_block_device {
    volume_size = 16
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    instance_metadata_tags      = "disabled"
  }

  tags = {
    Name = var.project_name
  }

  lifecycle {
    precondition {
      condition     = var.allowed_aws_account_id == "" || data.aws_caller_identity.current.account_id == var.allowed_aws_account_id
      error_message = "Refusing to deploy outside the configured allowed_aws_account_id."
    }

    precondition {
      condition     = data.aws_region.current.name == "us-east-2"
      error_message = "Refusing to deploy outside us-east-2."
    }

    precondition {
      condition     = length(aws_security_group.instance.ingress) == 0
      error_message = "Instance security group must not define inbound rules."
    }

    precondition {
      condition     = !var.daal_enabled || var.daal_contract_address != ""
      error_message = "daal_contract_address is required when daal_enabled is true."
    }

    precondition {
      condition     = !var.daal_enabled || var.daal_provider_mode != "cdp" || var.cdp_evm_account_address != ""
      error_message = "cdp_evm_account_address is required when daal_enabled is true and daal_provider_mode is cdp."
    }
  }
}

module "guardduty" {
  source = "./modules/guardduty"

  project_name                 = var.project_name
  enabled                      = var.guardduty_enabled
  finding_publishing_frequency = var.guardduty_finding_publishing_frequency
}

module "cloudwatch" {
  source = "./modules/cloudwatch"

  project_name            = var.project_name
  aws_region              = var.aws_region
  instance_id             = aws_instance.provisioner.id
  vpc_id                  = aws_vpc.main.id
  vpc_flow_log_group_name = aws_cloudwatch_log_group.vpc_flow_logs.name
  guardduty_detector_id   = module.guardduty.detector_id
  alarm_actions           = var.cloudwatch_alarm_actions
}
