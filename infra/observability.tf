resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"

  tags = { Name = "${var.name_prefix}-alerts" }
}

# Optional so `terraform apply` works before you've decided who gets
# paged - but the alarms are pointless without a subscriber, so set this
# in terraform.tfvars before demo day.
resource "aws_sns_topic_subscription" "alerts_email" {
  count = var.alarm_notification_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_notification_email
}

# --- Alarm 1: 5xx errors from the API ---
resource "aws_cloudwatch_metric_alarm" "high_5xx" {
  alarm_name          = "${var.name_prefix}-high-5xx"
  alarm_description   = "TicketDesk API is returning 5xx responses"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = { Name = "${var.name_prefix}-high-5xx" }
}

# --- Alarm 2: unhealthy targets ---
resource "aws_cloudwatch_metric_alarm" "unhealthy_targets" {
  alarm_name          = "${var.name_prefix}-unhealthy-targets"
  alarm_description   = "One or more ECS tasks are failing the ALB health check"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  dimensions = {
    LoadBalancer = aws_lb.main.arn_suffix
    TargetGroup  = aws_lb_target_group.app.arn_suffix
  }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = { Name = "${var.name_prefix}-unhealthy-targets" }
}

# --- Alarm 3: high database CPU ---
resource "aws_cloudwatch_metric_alarm" "rds_high_cpu" {
  alarm_name          = "${var.name_prefix}-rds-high-cpu"
  alarm_description   = "RDS CPU utilization is sustained above 80%"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  # FIX: aws_db_instance.main.id resolves to RDS's internal DbiResourceId
  # ("db-XXXX...", an opaque immutable ID) in this provider version, not
  # the human-readable instance identifier ("tkt-dev-db") that AWS/RDS
  # CloudWatch metrics are actually published under. With .id here, this
  # alarm's dimension never matched any real metric data - it silently
  # sat on zero datapoints forever, `treat_missing_data = "notBreaching"`
  # kept it looking healthy, and it would never have fired even under a
  # genuine sustained-CPU incident. Found by deliberately stress-testing
  # RDS CPU to >80% for 20+ minutes (confirmed via raw
  # `aws cloudwatch get-metric-statistics` against the correct
  # identifier) and observing the alarm never left OK. `.identifier` is
  # the attribute that actually matches the CloudWatch dimension.
  dimensions = { DBInstanceIdentifier = aws_db_instance.main.identifier }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]

  tags = { Name = "${var.name_prefix}-rds-high-cpu" }
}

# --- Dashboard: request count, error rate, latency, CPU/memory, DB connections ---
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.name_prefix}-ticketdesk"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Request count & 5xx errors"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.main.arn_suffix, { stat = "Sum" }],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", aws_lb.main.arn_suffix, { stat = "Sum" }],
          ]
          period = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Response time (p50 / p99)"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.main.arn_suffix, { stat = "p50" }],
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.main.arn_suffix, { stat = "p99" }],
          ]
          period = 60
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "ECS CPU / memory utilization"
          region = var.aws_region
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name, { stat = "Average" }],
            ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name, { stat = "Average" }],
          ]
          period = 60
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Database connections & CPU"
          region = var.aws_region
          metrics = [
            # FIX: same wrong-attribute bug as the alarm above (.id is
            # RDS's internal resource ID, not the CloudWatch dimension
            # value) - this panel has been showing no data since deploy.
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", aws_db_instance.main.identifier, { stat = "Average" }],
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.main.identifier, { stat = "Average" }],
          ]
          period = 60
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 24
        height = 6
        properties = {
          title  = "Healthy vs. unhealthy targets"
          region = var.aws_region
          metrics = [
            ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", aws_lb.main.arn_suffix, "TargetGroup", aws_lb_target_group.app.arn_suffix, { stat = "Average" }],
            ["AWS/ApplicationELB", "UnHealthyHostCount", "LoadBalancer", aws_lb.main.arn_suffix, "TargetGroup", aws_lb_target_group.app.arn_suffix, { stat = "Average" }],
          ]
          period = 60
        }
      },
    ]
  })
}
