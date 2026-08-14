# Known gaps and in-progress items

Honest record of what isn't finished and why, per the brief's own guidance:
an explained gap earns more than a silent one.

## Deploy status: live, pushed, applied, verified end to end

Everything below is committed on `main`, applied to the real AWS account
via `terraform apply`, and deployed through `deploy.yml`'s full pipeline
(test -> secret-scan -> build -> deploy -> smoke-test, all green). The
running app was manually verified against live AWS - not just CI green -
covering register/login, role-scoped routing, ticket lifecycle, agent
status transitions, comments, real S3 presigned-upload attachments, the
Lambda thumbnailer, and in-app notifications. Two real bugs were found
only under live testing and fixed: a stale-schema RDS table (created by
an early placeholder image, predating the current models) and a
stale-render race condition in the frontend (async view updates firing
after the user had already navigated away). This is a POC meant to be
destroyed between sessions - see infra/README.md's cost note - so treat
"live" as "live until the next `terraform destroy`," not permanent.

## CI/CD (M6): OIDC federation blocked at the AWS account level

**Status: infrastructure and workflow are fully built and believed correct;
blocked on an AWS-side account restriction, not a code/config bug.**

`deploy.yml`'s `build-and-push` job fails at "Configure AWS credentials
(OIDC)" with:

```
Error: Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity
```

What's been verified correct, not just assumed:

- The IAM role's trust policy (`infra/github_oidc.tf`) matches the actual
  OIDC token's claims exactly - confirmed by decoding the real token
  GitHub issues (`job_workflow_ref`, `repository`, `aud` all match the
  policy's conditions byte-for-byte).
- Two real bugs *were* found and fixed along the way: GitHub embeds
  numeric owner/repo IDs into the `sub` claim on this repo
  (`repo:owner@123/repo@456:ref:...`), which broke a naive `sub` match;
  and AWS requires a trust policy to be scoped by `sub` or
  `job_workflow_ref` specifically, rejecting a `repository`-only
  condition outright. Both are fixed in the current `github_oidc.tf`.
- CloudTrail confirms the actual STS call: `errorCode: AccessDenied`,
  `errorMessage: "An unknown error occurred"` - which is AWS deliberately
  withholding the real reason from unauthorized callers, not a logging
  gap on our end.

This same AWS account already hit one other account-level restriction
earlier (`CreateDistributionWithTags` for CloudFront returned
`AccessDenied: Your account must be verified`), which AWS Support
resolved directly. Given the trust policy is provably correct and the
generic denial reason matches that same class of problem, the working
hypothesis is another account-level hold - plausibly an anti-fraud
restriction on OIDC federation for new/free-tier accounts - rather than
anything fixable in Terraform.

**Action taken:** AWS Support isn't reliably usable in this environment
(sandbox/free-tier constraints), so rather than leave the pipeline
blocked indefinitely, `deploy.yml` now authenticates with a scoped IAM
user access key (`infra/github_actions_iam_user.tf`) instead of OIDC -
same exact permission scope as the OIDC role, just a long-lived
credential stored as a GitHub *secret* rather than a short-lived
federated token. Free Tier: costs nothing either way. The OIDC role and
provider are still deployed, unused, ready to switch back to (the
commented-out block is right there in `deploy.yml`) if the account
restriction ever turns out to be liftable.

This is a deliberate, documented substitution for an environment
constraint - not the preferred pattern, and worth saying so on demo day
rather than presenting it as the original design.

## Everything else - status

- M0-M5 (individual): confirmed working against real AWS - ALB health
  check, DB connectivity, ticket CRUD, attachments via presigned S3
  upload with Lambda thumbnailing, all manually verified end to end.
- Auth: JWT login/register/roles (`src/security.py`,
  `src/routers/auth.py`). `infra/secrets.tf` provisions a
  Terraform-generated `JWT_SECRET` in Secrets Manager, wired into the
  ECS task the same way `DB_PASSWORD` is - never baked into the image or
  typed in by hand. Applied and verified live.
- Lambda thumbnailer CI/CD: automated in `deploy.yml` as its own
  `build-and-deploy-lambda` job (parallel to the API's build-and-push,
  since they're independent services). Exercised by real pipeline runs -
  green, and the deployed thumbnail renders on the live ticket page.
- Attachments bucket CORS: computed from the frontend bucket's own
  `website_endpoint` (`attachments_cors_allowed_origins`) rather than a
  hand-set `"*"` - no manual two-step apply needed to tighten it.
- M7 (observability): dashboard and 3 alarms deployed; alarm-trip test
  not yet performed.
- M8 (hardening/cost/teardown): tagging is live via provider
  `default_tags`; cost allocation tag activation, budget, cost report,
  and load testing were never part of the original ask and remain out of
  scope. A destroy/rebuild rehearsal is possible via `infra/destroy.sh`
  but hasn't been run yet - pending explicit go-ahead, since it tears
  down real billable resources.
