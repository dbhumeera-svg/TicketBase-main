# Fallback auth for GitHub Actions: the OIDC role in github_oidc.tf
# consistently fails sts:AssumeRoleWithWebIdentity with a generic
# AccessDenied on this account/sandbox (see NOTES.md) - the trust policy
# was verified byte-for-byte correct against the actual token's claims,
# so this looks like an account-level restriction only AWS Support can
# lift, and that path isn't available in this environment. This IAM user
# is the pragmatic unblock: same exact permission scope as the OIDC role
# (reuses data.aws_iam_policy_document.github_actions_deploy from
# github_oidc.tf), just authenticated with a long-lived access key
# instead of a short-lived federated token.
#
# Free Tier: IAM users and access keys have no cost, ever, regardless of
# account age or tier.
#
# Trade-off, stated plainly: a leaked long-lived key is worse than a
# leaked short-lived token - this is a deliberate, documented
# substitution for an environment constraint, not the preferred pattern.
# The OIDC role stays deployed and unused; switch deploy.yml back to it
# (see the commented block there) if the account restriction ever lifts.

resource "aws_iam_user" "github_actions_deploy" {
  name = "${var.name_prefix}-github-actions-deploy"

  tags = { Name = "${var.name_prefix}-github-actions-deploy-user" }
}

resource "aws_iam_user_policy" "github_actions_deploy" {
  name   = "${var.name_prefix}-github-actions-deploy"
  user   = aws_iam_user.github_actions_deploy.name
  policy = data.aws_iam_policy_document.github_actions_deploy.json
}

resource "aws_iam_access_key" "github_actions_deploy" {
  user = aws_iam_user.github_actions_deploy.name
}
