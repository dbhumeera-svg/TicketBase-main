resource "aws_ecs_cluster" "main" {
  name = "${var.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${var.name_prefix}-cluster" }
}

resource "aws_ecs_task_definition" "app" {
  family                   = "${var.name_prefix}-ticketdesk"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "ticketdesk-api"
      image     = var.container_image
      essential = true

      portMappings = [
        {
          containerPort = var.container_port
          protocol      = "tcp"
        }
      ]

      # Not a secret - just tells the running app which environment it's
      # in. src/main.py reads this to gate demo admin/agent/user seeding
      # (skipped entirely outside "prod"/production-equivalent runs) and
      # src/security.py uses it to require JWT_SECRET be explicitly set
      # rather than silently generating a throwaway one.
      environment = [
        { name = "ENVIRONMENT", value = var.environment },
      ]

      # All config comes from Parameter Store / Secrets Manager at
      # container start, resolved by the execution role above - never
      # baked into the image or set as a plaintext env var (checklist
      # items 17-19). src/database.py assembles DATABASE_URL from these.
      secrets = [
        { name = "DB_HOST", valueFrom = aws_ssm_parameter.db_host.arn },
        { name = "DB_PORT", valueFrom = aws_ssm_parameter.db_port.arn },
        { name = "DB_NAME", valueFrom = aws_ssm_parameter.db_name.arn },
        { name = "DB_USER", valueFrom = aws_ssm_parameter.db_user.arn },
        { name = "CORS_ORIGINS", valueFrom = aws_ssm_parameter.cors_origins.arn },
        { name = "ATTACHMENTS_BUCKET", valueFrom = aws_ssm_parameter.attachments_bucket.arn },
        { name = "DB_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn },
        { name = "JWT_SECRET", valueFrom = aws_secretsmanager_secret.jwt_secret.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ticketdesk"
        }
      }
    }
  ])

  tags = { Name = "${var.name_prefix}-ticketdesk-task" }
}

resource "aws_ecs_service" "app" {
  name            = "${var.name_prefix}-ticketdesk-svc"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_task.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "ticketdesk-api"
    container_port   = var.container_port
  }

  # Gives the container time to boot before the ALB health check can fail
  # it and the deployment loops forever pulling it back down.
  health_check_grace_period_seconds = 60

  # Nothing here references these by attribute, so Terraform's own
  # dependency graph doesn't know the service has to wait for them - but
  # the first task Fargate launches genuinely needs the execution role's
  # permissions attached AND the VPC interface endpoints (ECR api/dkr,
  # logs, secrets, ssm) actually resolvable, or it fails with
  # CannotPullContainerError / ResourceInitializationError before it ever
  # gets a chance to retry into a working state. Without this, apply can
  # create the service in parallel with those and race it.
  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy_attachment.execution_managed,
    aws_iam_role_policy.execution_secrets,
    aws_iam_role_policy.task_attachments,
    aws_vpc_endpoint.interface,
    aws_vpc_endpoint.s3,
  ]

  tags = { Name = "${var.name_prefix}-ticketdesk-svc" }
}
