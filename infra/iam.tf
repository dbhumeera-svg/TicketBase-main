data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: used by the ECS agent itself to pull the image, ship
# logs, and resolve the `secrets` block in the task definition. This is
# NOT the app's runtime identity.
resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = { Name = "${var.name_prefix}-ecs-execution-role" }
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Scoped to the exact secret/parameters this task needs - no "*" resource
# (checklist item 32, pass/fail gate 2).
data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "ReadDbPassword"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db_password.arn]
  }

  statement {
    sid     = "ReadAppParameters"
    actions = ["ssm:GetParameters"]
    resources = [
      aws_ssm_parameter.db_host.arn,
      aws_ssm_parameter.db_port.arn,
      aws_ssm_parameter.db_name.arn,
      aws_ssm_parameter.db_user.arn,
      aws_ssm_parameter.cors_origins.arn,
      aws_ssm_parameter.attachments_bucket.arn,
    ]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${var.name_prefix}-ecs-execution-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# Task role: the app's own runtime identity. Config and the DB password
# arrive via the execution role's `secrets` injection above, but M5's
# presigned URLs are different: boto3 signs them locally using *this*
# role's credentials, and S3 checks *this* role's permissions when the
# browser actually uses the URL - generating a valid-looking signature
# isn't enough on its own.
resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = { Name = "${var.name_prefix}-ecs-task-role" }
}

data "aws_iam_policy_document" "task_attachments" {
  statement {
    sid = "PresignedUploadsAndDownloads"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
    ]
    resources = ["${aws_s3_bucket.attachments.arn}/*"]
  }
}

resource "aws_iam_role_policy" "task_attachments" {
  name   = "${var.name_prefix}-ecs-task-attachments"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_attachments.json
}
