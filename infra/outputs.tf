output "aws_region" {
  value = var.aws_region
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "alb_dns_name" {
  description = "Load balancer URL - hit this to reach the API."
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  description = "Push images here, tagged with the git commit SHA."
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}

output "target_group_arn" {
  value = aws_lb_target_group.app.arn
}

output "db_endpoint" {
  description = "RDS address (host only, no credentials)."
  value       = aws_db_instance.main.address
  sensitive   = true
}

output "cloudwatch_log_group" {
  value = aws_cloudwatch_log_group.app.name
}

output "cloudwatch_dashboard_url" {
  value = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

output "sns_alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "github_actions_role_arn" {
  description = "Set this as the AWS_DEPLOY_ROLE_ARN GitHub Actions repo variable."
  value       = aws_iam_role.github_actions_deploy.arn
}

output "attachments_bucket" {
  value = aws_s3_bucket.attachments.id
}

output "frontend_url" {
  description = "Open this for the app. Separate origin from the API now (no CloudFront) - the browser calls alb_dns_name directly, allowed via CORS_ORIGINS."
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

output "frontend_bucket" {
  value = aws_s3_bucket.frontend.id
}

output "lambda_thumbnail_ecr_repository_url" {
  description = "Push the thumbnailer image here, tagged with the git commit SHA."
  value       = aws_ecr_repository.lambda_thumbnail.repository_url
}
