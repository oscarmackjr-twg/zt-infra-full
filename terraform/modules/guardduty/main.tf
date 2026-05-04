resource "aws_guardduty_detector" "this" {
  enable                       = var.enabled
  finding_publishing_frequency = var.finding_publishing_frequency

  datasources {
    s3_logs {
      enable = true
    }
    kubernetes {
      audit_logs {
        enable = false
      }
    }
    malware_protection {
      scan_ec2_instance_with_findings {
        ebs_volumes {
          enable = true
        }
      }
    }
  }

  tags = {
    Name = "${var.project_name}-guardduty"
  }
}
