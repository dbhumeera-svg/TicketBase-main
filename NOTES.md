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
- M7 (observability): dashboard and 3 alarms deployed. **Alarm-trip test
  done 2026-08-14** - all three deliberately triggered and confirmed
  ALARM, one at a time, against the real deployment, then returned to
  normal. Evidence in `infra/EVIDENCE/alarms/`:
  - `01_unhealthy_target_test.log` - revoked the ALB->ECS security group
    rule; target went unhealthy, alarm tripped within ~5 minutes;
    restored and reconciled through Terraform.
  - `02_5xx_test.log` - real, hard-won: revoking the ECS->RDS security
    group rule alone did *not* trip this alarm, because SQLAlchemy's
    already-established connection pool survives security-group changes
    (SGs only block *new* connections) and the default pool has more
    than enough warm capacity to serve load without ever opening one.
    Fixed by actually stopping the RDS instance (`aws rds
    stop-db-instance`), which does terminate existing connections -
    that produced real, fast `503`s, tripped the alarm on the first
    evaluation, then RDS was started back up and the app redeployed
    with fresh connections.
  - `03_rds_cpu_test.log` - the one that actually justified doing this
    exercise for real instead of trusting the deployed alarms as
    correct. A one-off ECS task ran 4 parallel connections executing a
    CPU-heavy `generate_series` aggregation against RDS; raw
    `aws cloudwatch get-metric-statistics` confirmed real, sustained
    81-85% CPU for over 20 minutes - well past the 80%/3-period
    threshold - yet `tkt-dev-rds-high-cpu` stayed `OK` the entire time,
    with the same stale evaluation timestamp from the moment it was
    created during the rebuild. The alarm's `DBInstanceIdentifier`
    dimension (`infra/observability.tf`) was set to
    `aws_db_instance.main.id`, which this provider version resolves to
    RDS's internal, opaque `DbiResourceId` (`db-XXXX...`) - not the
    human-readable identifier (`tkt-dev-db`) that `AWS/RDS` CloudWatch
    metrics are actually published under. The alarm had been watching a
    dimension value that no metric would ever match; combined with
    `treat_missing_data = "notBreaching"`, it would have sat green
    forever, including through a genuine production CPU incident. The
    same wrong attribute also silently broke the dashboard's "Database
    connections & CPU" panel (it's been showing no data since deploy).
    Fixed (`.id` -> `.identifier`, all 3 occurrences) and reapplied, then
    re-ran the stress test end to end: alarm reached real `ALARM` within
    one evaluation cycle of the corrected dimension receiving data, app
    stayed fully healthy (`/api/health` and `/api/health/database` both
    `200`) throughout the stress, and the alarm recovered once the
    stress task's internal timer stopped it. This is the whole reason
    checklist item 30 says "deliberately trigger" and not "confirm the
    alarm resource exists" - a plausible-looking, deployed-and-never-
    tested alarm was, in fact, completely non-functional.
- M8 (hardening/cost/teardown):
  - Tagging is live via provider `default_tags`.
  - **Cost allocation tags activated 2026-08-14** (`Environment`,
    `Project`, `Owner`, `CostCenter`, `Name` - were `Inactive` since
    account creation, activated via `aws ce
    update-cost-allocation-tags-status`). Tag-based cost attribution is
    not retroactive, so today's near-zero total isn't yet a meaningful
    tag-scoped sample, but the filter is live going forward.
  - **Budget created 2026-08-14**: `TicketDesk-POC-Budget`, $25/month,
    scoped to the `Project=TicketDesk` tag, 80%-threshold email alert.
  - **Cost report written 2026-08-14**: `infra/COST_REPORT.md` - actual
    spend, top-2-most-expensive-by-design, and the full 24/7 cost table.
  - **Load test done 2026-08-14**: 20 concurrent simulated users for 5
    minutes against the live ALB (`/api/health` and
    `/api/health/database`), zero errors. Results in
    `infra/EVIDENCE/load-test/01_load_test_results.txt`.
  - **Destroy/rebuild rehearsal done 2026-08-14** (checklist item 9,
    pass/fail gate 4 and 5): `terraform destroy` then `terraform apply`
    from zero, app verified fully working again (health check, login,
    ticket, real S3 attachment upload, Lambda-generated thumbnail).
    Evidence and a full account of what actually went wrong along the
    way (not a clean run - see below) are in
    `infra/EVIDENCE/destroy-rebuild/`.

## Real problems hit during the 2026-08-14 destroy/rebuild rehearsal

Per this file's own stated policy, these are recorded because they're
real and because a future rebuild will hit the same class of problem if
the causes aren't understood - not because anything here reflects a
lasting defect in the Terraform config itself.

1. **A local DNS resolution failure interrupted the first `terraform
   destroy` mid-run** (`dial tcp: lookup ec2.us-east-1.amazonaws.com: no
   such host`, and the same for the S3 state backend and the DynamoDB
   lock table) - a transient problem with the machine running Terraform,
   not AWS. Recovery required: force-unlocking the stuck DynamoDB lock
   (verified it was this same interrupted run's lock, not a concurrent
   operator, before unlocking), pushing the local `errored.tfstate`
   Terraform had saved on write-failure to reconcile the remote backend
   (confirmed accurate against live AWS resource state first via direct
   `aws` CLI checks, not assumed), then safely resuming and completing
   the destroy.
2. **A real chicken-and-egg dependency deadlock** surfaced on the
   rebuild: `terraform apply` correctly refused to create the
   `github_actions_deploy` IAM policy (the one CI needs to push images)
   because that policy's Lambda-permissions statement references
   `aws_lambda_function.thumbnail.arn` - and the Lambda function itself
   failed to create because the freshly-recreated, empty ECR repo had no
   image in it yet. CI couldn't push the missing image because it didn't
   have the IAM policy yet either. Broken by pushing both images
   directly from a local Docker install using broader admin AWS
   credentials (not the CI pipeline's scoped deploy user, which didn't
   exist with working permissions yet), which let `terraform apply`
   finish creating everything, including the previously-blocked IAM
   policy.
3. **The local Docker build initially produced an image AWS Lambda
   rejected outright** - `CreateFunction` returned "The image manifest,
   config or layer media type for the source image ... is not
   supported." Modern Docker Desktop (BuildKit with the containerd image
   store) attaches an OCI provenance/SBOM attestation manifest by
   default, which Lambda's container-image support doesn't understand -
   this is why the same Dockerfile has always built fine in CI (GitHub's
   runner doesn't attach attestations by default). Fixed with `docker
   build --provenance=false --sbom=false`. Since the ECR repo has
   immutable tags, the already-pushed bad image had to be deleted
   (`aws ecr batch-delete-image`) before the corrected one could be
   pushed under the same tag.
4. **Two separate Docker Desktop backend processes ended up running at
   once** after a first launch attempt appeared to fail silently and was
   relaunched - this caused mysterious, repeatable "broken pipe"/"closed
   network connection" errors on the exact same image layer across
   several push retries. Fixed by killing all `docker*`/`com.docker.*`
   processes and relaunching once, cleanly.
