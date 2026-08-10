# Password: Secrets Manager (checklist item 17).
resource "aws_secretsmanager_secret" "db_password" {
  name = "${var.name_prefix}/db-password"

  # A POC gets destroyed and recreated often; the default 30-day recovery
  # window would block reusing the same secret name on the next apply.
  recovery_window_in_days = 0

  tags = { Name = "${var.name_prefix}-db-password" }
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

# Everything else: Parameter Store (checklist item 18). None of this is
# secret - the ECS task execution role fetches it at container start and
# injects it as an env var, same mechanism as the password above.
resource "aws_ssm_parameter" "db_host" {
  name  = "/${var.name_prefix}/db/host"
  type  = "String"
  value = aws_db_instance.main.address

  tags = { Name = "${var.name_prefix}-db-host" }
}

resource "aws_ssm_parameter" "db_port" {
  name  = "/${var.name_prefix}/db/port"
  type  = "String"
  value = tostring(aws_db_instance.main.port)

  tags = { Name = "${var.name_prefix}-db-port" }
}

resource "aws_ssm_parameter" "db_name" {
  name  = "/${var.name_prefix}/db/name"
  type  = "String"
  value = var.db_name

  tags = { Name = "${var.name_prefix}-db-name" }
}

resource "aws_ssm_parameter" "db_user" {
  name  = "/${var.name_prefix}/db/username"
  type  = "String"
  value = var.db_username

  tags = { Name = "${var.name_prefix}-db-username" }
}

resource "aws_ssm_parameter" "cors_origins" {
  name  = "/${var.name_prefix}/app/cors-origins"
  type  = "String"
  # Frontend and API are on separate origins (S3 website endpoint vs.
  # ALB DNS name - no CloudFront in front to unify them), so this has to
  # be real, not "*", for the browser to accept cross-origin fetches.
  value = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"

  tags = { Name = "${var.name_prefix}-cors-origins" }
}

resource "aws_ssm_parameter" "attachments_bucket" {
  name  = "/${var.name_prefix}/app/attachments-bucket"
  type  = "String"
  value = aws_s3_bucket.attachments.id

  tags = { Name = "${var.name_prefix}-attachments-bucket" }
}
