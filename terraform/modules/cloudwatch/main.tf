locals {
  metric_namespace = "${var.project_name}/compliance"
}

resource "aws_cloudwatch_log_metric_filter" "vpc_rejects" {
  name           = "${var.project_name}-vpc-flow-rejects"
  log_group_name = var.vpc_flow_log_group_name
  pattern        = "[version, account, interface_id, srcaddr, dstaddr, srcport, dstport, protocol, packets, bytes, start, end, action = \"REJECT\", log_status]"

  metric_transformation {
    name      = "VpcFlowRejectedPackets"
    namespace = local.metric_namespace
    value     = "$packets"
  }
}

resource "aws_cloudwatch_metric_alarm" "ec2_status_check_failed" {
  alarm_name          = "${var.project_name}-ec2-status-check-failed"
  alarm_description   = "EC2 status checks failed for ${var.instance_id}."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.alarm_actions

  dimensions = {
    InstanceId = var.instance_id
  }
}

resource "aws_cloudwatch_metric_alarm" "vpc_flow_reject_spike" {
  alarm_name          = "${var.project_name}-vpc-flow-reject-spike"
  alarm_description   = "VPC Flow Logs are reporting rejected packets."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = aws_cloudwatch_log_metric_filter.vpc_rejects.metric_transformation[0].name
  namespace           = local.metric_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 100
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.alarm_actions
}

resource "aws_cloudwatch_dashboard" "compliance" {
  dashboard_name = "${var.project_name}-continuous-compliance"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 3
        properties = {
          markdown = "# ${var.project_name} Continuous Compliance\nRegion: ${var.aws_region}\nVPC: ${var.vpc_id}\nInstance: ${var.instance_id}\nGuardDuty detector: ${var.guardduty_detector_id}"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 3
        width  = 12
        height = 6
        properties = {
          title   = "EC2 Status Checks"
          region  = var.aws_region
          stat    = "Maximum"
          period  = 60
          view    = "timeSeries"
          metrics = [["AWS/EC2", "StatusCheckFailed", "InstanceId", var.instance_id]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 3
        width  = 12
        height = 6
        properties = {
          title   = "VPC Flow Log Rejects"
          region  = var.aws_region
          stat    = "Sum"
          period  = 300
          view    = "timeSeries"
          metrics = [[local.metric_namespace, "VpcFlowRejectedPackets"]]
        }
      },
      {
        type   = "log"
        x      = 0
        y      = 9
        width  = 24
        height = 8
        properties = {
          title  = "Recent VPC Flow Log Rejects"
          region = var.aws_region
          view   = "table"
          query  = "SOURCE '${var.vpc_flow_log_group_name}' | fields @timestamp, @message | filter @message like / REJECT / | sort @timestamp desc | limit 20"
        }
      }
    ]
  })
}
