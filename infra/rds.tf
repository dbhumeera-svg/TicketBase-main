resource "random_password" "db" {
  length  = 24
  # Keep it psycopg2/URL-safe; the app builds a DATABASE_URL from this at
  # runtime and special characters would need percent-encoding.
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = aws_subnet.private[*].id

  tags = { Name = "${var.name_prefix}-db-subnets" }
}

resource "aws_db_instance" "main" {
  identifier = "${var.name_prefix}-db"
  engine     = "postgres"
  # engine_version intentionally omitted: AWS picks its current default
  # Postgres version, so this doesn't go stale or fail against a region
  # where a hardcoded version number isn't offered.
  instance_class = var.db_instance_class

  allocated_storage = var.db_allocated_storage
  storage_type       = "gp2"
  storage_encrypted  = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  # Prod always keeps at least 7 days of backups regardless of what
  # backup_retention_days happens to be set to - a safety floor, not a
  # ceiling (a higher var.backup_retention_days value still wins).
  backup_retention_period = (
    var.environment == "prod"
    ? max(var.backup_retention_days, 7)
    : var.backup_retention_days
  )
  multi_az = false

  # dev/test is a POC that gets destroyed and rebuilt repeatedly
  # (checklist item 9, pass/fail gate 5) - skip_final_snapshot +
  # deletion_protection = false there trades production safety for a
  # clean `terraform destroy`. The moment var.environment = "prod",
  # both flip: deletion_protection makes AWS itself refuse to delete
  # this instance (via Terraform, the console, or the CLI) until it's
  # explicitly turned off first, and a final snapshot is taken if it
  # ever is. infra/destroy.sh's production confirmation prompt is the
  # human-facing layer on top of this AWS-enforced one.
  skip_final_snapshot = var.environment != "prod"
  deletion_protection = var.environment == "prod"

  tags = { Name = "${var.name_prefix}-db" }
}
