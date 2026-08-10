# Bare security groups with no inline rules. Rules are separate
# aws_vpc_security_group_*_rule resources below so they can reference each
# other's SG IDs without Terraform seeing a dependency cycle (checklist
# item 12: reference other security groups, not 0.0.0.0/0 - the only CIDR
# rule in this file is the ALB's public HTTP listener, which has to be
# reachable from the internet by definition).

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "Internet-facing ALB for the TicketDesk API"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.name_prefix}-alb-sg" }
}

resource "aws_security_group" "ecs_task" {
  name        = "${var.name_prefix}-ecs-task-sg"
  description = "TicketDesk API tasks (private subnet)"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.name_prefix}-ecs-task-sg" }
}

resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "TicketDesk PostgreSQL database (private subnet)"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.name_prefix}-rds-sg" }
}

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name_prefix}-vpce-sg"
  description = "Interface VPC endpoints (ECR, logs, Secrets Manager, SSM)"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "${var.name_prefix}-vpce-sg" }
}

# --- ALB ---

resource "aws_vpc_security_group_ingress_rule" "alb_http_in" {
  security_group_id = aws_security_group.alb.id
  description        = "HTTP from the internet"
  cidr_ipv4          = "0.0.0.0/0"
  from_port          = 80
  to_port             = 80
  ip_protocol        = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_ecs" {
  security_group_id            = aws_security_group.alb.id
  description                   = "To ECS tasks"
  referenced_security_group_id = aws_security_group.ecs_task.id
  from_port                     = var.container_port
  to_port                       = var.container_port
  ip_protocol                   = "tcp"
}

# --- ECS tasks ---

resource "aws_vpc_security_group_ingress_rule" "ecs_from_alb" {
  security_group_id            = aws_security_group.ecs_task.id
  description                   = "From the ALB only"
  referenced_security_group_id = aws_security_group.alb.id
  from_port                     = var.container_port
  to_port                       = var.container_port
  ip_protocol                   = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_rds" {
  security_group_id            = aws_security_group.ecs_task.id
  description                   = "To the database"
  referenced_security_group_id = aws_security_group.rds.id
  from_port                     = 5432
  to_port                       = 5432
  ip_protocol                   = "tcp"
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_vpce" {
  security_group_id            = aws_security_group.ecs_task.id
  description                   = "To VPC interface endpoints"
  referenced_security_group_id = aws_security_group.vpc_endpoints.id
  from_port                     = 443
  to_port                       = 443
  ip_protocol                   = "tcp"
}

# The S3 GATEWAY endpoint (endpoints.tf) doesn't terminate at an ENI with
# a security group like the interface endpoints above do - it's pure
# route-table redirection (see the prefix-list route Terraform adds to
# aws_route_table.private). That means THIS security group still
# evaluates that traffic against its real destination (S3's public IP
# range), and referencing vpc_endpoints's SG above does nothing for it.
# Without this rule, ECR image pulls fail with CannotPullContainerError /
# a TCP timeout, because layer bytes are actually served from S3, not
# the ecr.dkr endpoint itself - the SG was silently dropping that leg.
data "aws_ec2_managed_prefix_list" "s3" {
  name = "com.amazonaws.${var.aws_region}.s3"
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_s3_gateway" {
  security_group_id = aws_security_group.ecs_task.id
  description         = "To the S3 gateway endpoint (ECR image layers live in S3)"
  prefix_list_id     = data.aws_ec2_managed_prefix_list.s3.id
  from_port          = 443
  to_port             = 443
  ip_protocol        = "tcp"
}

# --- RDS ---

resource "aws_vpc_security_group_ingress_rule" "rds_from_ecs" {
  security_group_id            = aws_security_group.rds.id
  description                   = "From ECS tasks only"
  referenced_security_group_id = aws_security_group.ecs_task.id
  from_port                     = 5432
  to_port                       = 5432
  ip_protocol                   = "tcp"
}

# --- VPC endpoints ---

resource "aws_vpc_security_group_ingress_rule" "vpce_from_ecs" {
  security_group_id            = aws_security_group.vpc_endpoints.id
  description                   = "HTTPS from ECS tasks"
  referenced_security_group_id = aws_security_group.ecs_task.id
  from_port                     = 443
  to_port                       = 443
  ip_protocol                   = "tcp"
}
