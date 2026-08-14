# Replaces infrastructure/ticketdesk-infrastructure.yaml (CloudFormation).
# The brief requires everything in Terraform (checklist item 6) - keeping
# the registry in a second tool alongside it would mean two sources of
# truth for the same resource. Do not apply the old CloudFormation
# template against the same account; it would create a second, differently
# named ECR repo.

resource "aws_ecr_repository" "app" {
  name                 = "${var.name_prefix}-ticketdesk"
  image_tag_mutability = "IMMUTABLE"

  # Without this, `terraform destroy` fails once CI has pushed even one
  # image - a POC registry has no retention requirement that would argue
  # for the safer default.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = { Name = "${var.name_prefix}-ticketdesk" }
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name_prefix}-ticketdesk"
  retention_in_days = 14

  tags = { Name = "${var.name_prefix}-ticketdesk-logs" }
}
