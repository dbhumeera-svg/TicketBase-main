# M6: lets GitHub Actions assume an IAM role via OIDC federation - no
# long-lived AWS access key sitting in GitHub Secrets (Q4's correct
# answer, and pass/fail-adjacent: a leaked static key is a much worse
# incident than a leaked short-lived federated token).
#
# NOTE: an AWS account can only have one OIDC provider per unique URL.
# If your pod's account already has a
# "token.actions.githubusercontent.com" provider (common if anyone has
# set up GitHub Actions OIDC before), delete this resource block and
# replace `aws_iam_openid_connect_provider.github_actions.arn` below with
# the existing provider's ARN instead - or import it:
#   terraform import aws_iam_openid_connect_provider.github_actions <existing-arn>

data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates[0].sha1_fingerprint]

  tags = { Name = "${var.name_prefix}-github-oidc" }
}

data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github_actions.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to this exact repo, any branch/PR/tag.
    #
    # AWS requires an OIDC trust policy to constrain on `sub` or
    # `job_workflow_ref` specifically - a policy scoped only by
    # `repository`/`aud` is rejected outright at apply time
    # ("...must evaluate...sub or job_workflow_ref which is not scoped
    # to all"). `sub` isn't usable here though: GitHub embeds numeric
    # owner/repo IDs into it on this repo
    # ("repo:owner@123/repo@456:ref:..."), which silently breaks a plain
    # "repo:owner/repo:*" StringLike match with no error at apply time -
    # just a permanent, confusing AssumeRoleWithWebIdentity rejection at
    # workflow run time instead. `job_workflow_ref` stays a clean
    # "owner/repo/.github/workflows/file@ref" string with no ID
    # embedding, so it's used to satisfy AWS's requirement, with
    # `repository` layered on top as a second, simpler check.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:job_workflow_ref"
      values   = ["${var.github_repository}/.github/workflows/*"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:repository"
      values   = [var.github_repository]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy" {
  name               = "${var.name_prefix}-github-actions-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json

  tags = { Name = "${var.name_prefix}-github-actions-deploy" }
}

# Scoped to exactly what the pipeline does: push an image, register a new
# task definition revision, and roll the service to it. Two actions
# (ecr:GetAuthorizationToken, ecs:RegisterTaskDefinition/
# DescribeTaskDefinition) are "*"-resource by AWS API design, not a
# choice made here - neither supports resource-level permissions.
data "aws_iam_policy_document" "github_actions_deploy" {
  statement {
    sid       = "ECRAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "ECRPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:BatchGetImage",
    ]
    resources = [
      aws_ecr_repository.app.arn,
      aws_ecr_repository.lambda_thumbnail.arn,
    ]
  }

  statement {
    sid = "ECSRegisterTaskDefinition"
    actions = [
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "ECSUpdateService"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [aws_ecs_service.app.id]
  }

  statement {
    sid       = "PassEcsRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.task.arn]
  }

  statement {
    sid       = "UpdateThumbnailLambda"
    actions   = ["lambda:UpdateFunctionCode", "lambda:GetFunction"]
    resources = [aws_lambda_function.thumbnail.arn]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name   = "${var.name_prefix}-github-actions-deploy"
  role   = aws_iam_role.github_actions_deploy.id
  policy = data.aws_iam_policy_document.github_actions_deploy.json
}
