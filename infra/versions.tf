terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Remote state with locking (checklist item 7). Fill these in after
  # running infra/bootstrap once, then `terraform init`. See infra/README.md.
  backend "s3" {
    # bucket         = "tkt-<your-initials>-tfstate"
    # key            = "ticketdesk/terraform.tfstate"
    # region         = "us-east-1"
    # dynamodb_table = "ticketdesk-tf-locks"
    # encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "TicketDesk"
      Owner       = var.owner
      Environment = var.environment
      CostCenter  = var.cost_center
    }
  }
}
