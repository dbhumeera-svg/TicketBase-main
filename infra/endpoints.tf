# Gateway endpoint for S3 - free, and required for the ECR image layer
# store (ECR backs onto S3) to be reachable without a NAT Gateway.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = { Name = "${var.name_prefix}-s3-endpoint" }
}

locals {
  interface_endpoints = {
    ecr_api        = "com.amazonaws.${var.aws_region}.ecr.api"
    ecr_dkr        = "com.amazonaws.${var.aws_region}.ecr.dkr"
    logs           = "com.amazonaws.${var.aws_region}.logs"
    secretsmanager = "com.amazonaws.${var.aws_region}.secretsmanager"
    ssm            = "com.amazonaws.${var.aws_region}.ssm"
  }
}

# Interface endpoints for everything else the ECS task needs at runtime:
# pulling its image (ecr.api/ecr.dkr), shipping logs, and reading secrets/
# config. Private DNS is enabled so the AWS SDK/CLI need no code changes -
# the standard service hostnames resolve to these endpoints inside the VPC.
#
# Deliberately ONE subnet, not both: interface endpoints have no free
# tier and bill per-AZ (~$0.01/hr each) - 5 endpoints x 2 AZs runs
# ~$72/month just sitting there, vs. ~$36/month for one AZ. A task in
# either private subnet can still reach it; it's not AZ-local traffic,
# just cross-AZ within the same VPC. For production you'd want both AZs
# so one AZ's endpoint ENI having an issue can't take down image pulls
# for tasks in the other AZ - not a meaningful risk for a POC that's
# usually torn down between demos anyway.
resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = aws_vpc.main.id
  service_name        = each.value
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private[0].id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.name_prefix}-${each.key}-endpoint" }
}
