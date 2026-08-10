# Known gaps and in-progress items

Honest record of what isn't finished and why, per the brief's own guidance:
an explained gap earns more than a silent one.

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

**Action taken:** AWS Support case filed (Account and Billing support),
same as the CloudFront resolution. Once resolved, the pipeline should
work with no further code changes - `terraform apply` + a push to `main`
should just go green.

**What still demonstrates M6 in the meantime:** the full pipeline design
(test -> secret-scan -> build -> deploy -> smoke-test, each gating the
next) is implemented and the `test`/`secret-scan` jobs run and pass on
every push - only the AWS-authenticated jobs are blocked.

## Everything else - status

- M0-M5 (individual): confirmed working against real AWS - ALB health
  check, DB connectivity, ticket CRUD, attachments via presigned S3
  upload with Lambda thumbnailing, all manually verified end to end.
- M7 (observability): dashboard and 3 alarms deployed; alarm-trip test
  not yet performed.
- M8 (hardening/cost/teardown): tagging is live via provider
  `default_tags`; cost allocation tag activation, budget, cost report,
  load test, and a full destroy/rebuild rehearsal are still open.
