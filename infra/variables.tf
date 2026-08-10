variable "name_prefix" {
  description = "Resource name prefix, e.g. tkt-<your-initials>. Keeps everyone's individually-deployed copy (M0-M5) from colliding in a shared pod account."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,20}$", var.name_prefix))
    error_message = "name_prefix must be lowercase alphanumeric/hyphen, starting with a letter (e.g. tkt-ab)."
  }
}

variable "owner" {
  description = "Your name or handle, used for the Owner tag on every resource."
  type        = string
}

variable "environment" {
  description = "Environment tag, e.g. dev."
  type        = string
  default     = "dev"
}

variable "cost_center" {
  description = "CostCenter tag used to isolate this POC's spend in Cost Explorer."
  type        = string
  default     = "ticketdesk-poc"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the two public subnets (ALB only)."
  type        = list(string)
  default     = ["10.20.0.0/24", "10.20.1.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for the two private subnets (ECS tasks + RDS)."
  type        = list(string)
  default     = ["10.20.10.0/24", "10.20.11.0/24"]
}

variable "container_port" {
  description = "Port the TicketDesk API container listens on (matches the Dockerfile EXPOSE)."
  type        = number
  default     = 8080
}

variable "container_image" {
  description = "Full ECR image URI including an immutable tag (git commit SHA) - never 'latest'. Built and pushed in M1/CI, before the ECS service can reach steady state."
  type        = string
}

variable "task_cpu" {
  description = "Fargate task vCPU units."
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Fargate task memory (MiB)."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Number of running tasks in the ECS service."
  type        = number
  default     = 1
}

variable "db_name" {
  description = "Application database name."
  type        = string
  default     = "ticketdesk"
}

variable "db_username" {
  description = "Application database username (not a secret by itself; the password is what's protected)."
  type        = string
  default     = "ticketdesk_app"
}

variable "db_instance_class" {
  description = "RDS instance class. db.t3.micro is free-tier eligible."
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GiB. 20 GiB is within the free tier."
  type        = number
  default     = 20
}

variable "backup_retention_days" {
  description = "Automated backup retention period in days (must be non-zero per checklist item 21)."
  type        = number
  default     = 1
}

variable "attachments_cors_allowed_origins" {
  description = "Origins allowed to PUT/POST/GET directly against the attachments bucket. Tighten to your frontend_url output once M4 is applied."
  type        = list(string)
  default     = ["*"]
}

variable "lambda_image" {
  description = "Full ECR image URI (with tag) for the thumbnail Lambda, built from lambda/thumbnail/. Same chicken-and-egg as container_image - see infra/README.md."
  type        = string
}

variable "alarm_notification_email" {
  description = "Email subscribed to the SNS alerts topic. Leave blank to create the alarms without a subscriber (you'll need to add one manually before they're useful)."
  type        = string
  default     = ""
}

variable "github_repository" {
  description = "GitHub repo allowed to assume the CI/CD deploy role via OIDC, as owner/repo (e.g. yourteam/ticketdesk)."
  type        = string
}
