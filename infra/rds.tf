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

  backup_retention_period = var.backup_retention_days
  multi_az                = false

  # This is a POC that gets destroyed and rebuilt repeatedly (checklist
  # item 9, pass/fail gate 5). skip_final_snapshot + deletion_protection =
  # false trade production safety for a clean `terraform destroy`. Flip
  # both before this ever holds real data.
  skip_final_snapshot = true
  deletion_protection = false

  tags = { Name = "${var.name_prefix}-db" }
}
