# TicketDesk infrastructure

Terraform for the whole POC brief architecture: VPC (2 public + 2 private
subnets across 2 AZs), an internet-facing ALB, an ECS Fargate service
running the API in a private subnet, RDS PostgreSQL (private, password in
Secrets Manager, other config in Parameter Store), an S3 static website
for the frontend, an S3 bucket + Lambda for attachment thumbnails,
CloudWatch dashboard + 3 alarms + SNS, and the GitHub Actions OIDC role
the CI/CD pipeline deploys with.

No NAT Gateway anywhere — private subnets reach ECR, CloudWatch Logs,
Secrets Manager and SSM through VPC interface endpoints instead.

**No CloudFront.** The frontend is a plain S3 static website
(`s3_frontend_website.tf`), on a different origin than the API (the ALB),
tied together with CORS instead of one CDN domain. This is a deliberate
Free Tier / simplicity trade — see "Cost reality check" below for why,
and `s3_frontend_website.tf`'s header comment for the checklist-item-22
trade-off it implies (bucket has to be public, read-only, static assets
only, zero secrets in it).

## Cost reality check — read this before you `apply`

Nothing here is free to run indefinitely. Free Tier only covers what the
table below marks ✅; everything else bills by the hour whether or not
anyone's looking at it.

| Resource | Free tier? | Approx. cost running 24/7 |
|---|---|---|
| 5 VPC interface endpoints × 1 AZ | ❌ None | ~$36/month |
| Application Load Balancer | ❌ None | ~$16/month |
| ECS Fargate task (256/512) | ❌ None | ~$9-10/month |
| Secrets Manager (1 secret) | ❌ None | ~$0.40/month |
| RDS `db.t3.micro`, single instance | ✅ 750 hrs/mo, first 12 mo | Free |
| S3 (frontend + attachments) | ✅ 5GB, 20k GET, 2k PUT/mo | Free at demo volume |
| Lambda (thumbnailer) | ✅ 1M requests/mo | Free at demo volume |
| CloudWatch (1 dashboard, 3 alarms) | ✅ 3 dashboards, 10 alarms free | Free |
| SNS | ✅ 1,000 email notifications/mo | Free at demo volume |
| ECR (2 repos) | ✅ 500MB/mo, first 12 mo | Free unless images pile up |

**The single most effective thing you can do:** `terraform destroy` when
you're not actively using it, `terraform apply` again before you need it.
The VPC endpoints + ALB + Fargate together run ~$60/month continuously —
destroying between sessions turns that into a few dollars for the hours
you actually spend developing and demoing.

## Layout

```
infra/
  bootstrap/               # one-time: S3 bucket + DynamoDB table for this stack's remote state
  versions.tf               # providers + backend "s3" block (fill in after bootstrap)
  variables.tf
  vpc.tf
  endpoints.tf               # VPC interface/gateway endpoints (NAT Gateway replacement)
  security_groups.tf
  alb.tf
  ecr.tf                     # app image repo + CloudWatch log group
  rds.tf
  secrets.tf                 # Secrets Manager (DB password) + Parameter Store (everything else)
  iam.tf                     # ECS execution role (scoped) + task role
  ecs.tf                      # cluster, task definition, service
  s3_attachments.tf           # M5: attachments bucket
  lambda_thumbnail.tf         # M5: container-image Lambda, S3 event trigger
  s3_frontend_website.tf      # M4: frontend bucket, S3 static website hosting (no CloudFront)
  observability.tf            # M7: dashboard, 3 alarms, SNS topic
  github_oidc.tf               # M6: OIDC provider + deploy role for GitHub Actions
  outputs.tf
  terraform.tfvars.example
```

## First-time setup

**1. Bootstrap the remote state backend** (once per AWS account / pod):

```bash
cd infra/bootstrap
terraform init
terraform apply -var="state_bucket_name=tkt-<your-initials>-tfstate"
```

Note the bucket and table names from the output.

**2. Point the main config at that backend:**

```bash
cd infra
terraform init \
  -backend-config="bucket=tkt-<your-initials>-tfstate" \
  -backend-config="key=ticketdesk/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=ticketdesk-tf-locks" \
  -backend-config="encrypt=true"
```

**3. Set your variables:**

```bash
cp terraform.tfvars.example terraform.tfvars
# edit name_prefix, owner, aws_region, alarm_notification_email, github_repository
```

`container_image` and `lambda_image` also need real values — see step 5
below; you can leave them pointing at a placeholder tag for the first
`apply` (the resources will exist, they just won't run anything yet).

## Deploying end to end

Order matters because ECS/Lambda need images that don't exist until ECR
does, which Terraform itself creates. Run this from `infra/`.

**4. Create everything except a working workload:**

```bash
terraform apply
```

The ECR repos, VPC, ALB, RDS, S3 buckets, IAM roles, dashboard and alarms
all get created. The ECS service and Lambda function exist but have
nothing runnable in them yet.

**5. Build and push the API image:**

```bash
REPO_URL=$(terraform output -raw ecr_repository_url)
REGION=$(terraform output -raw aws_region)
SHA=$(git rev-parse --short HEAD)
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REPO_URL"
docker build -t "$REPO_URL:$SHA" ..
docker push "$REPO_URL:$SHA"
```

**6. Build and push the thumbnail Lambda image:**

```bash
LAMBDA_REPO_URL=$(terraform output -raw lambda_thumbnail_ecr_repository_url)
docker build -t "$LAMBDA_REPO_URL:$SHA" ../lambda/thumbnail
docker push "$LAMBDA_REPO_URL:$SHA"
```

**7. Point Terraform at both real tags and re-apply:**

```bash
terraform apply \
  -var="container_image=$REPO_URL:$SHA" \
  -var="lambda_image=$LAMBDA_REPO_URL:$SHA"
```

This updates the ECS task definition (rolling the service to the new
image) and the Lambda function code.

**8. Upload the frontend and verify:**

The frontend files (`index.html`, `app.js`, `styles.css`, and a
Terraform-generated `config.js` pointing at the real ALB DNS name) are
uploaded to S3 as part of every `terraform apply` via `aws_s3_object`
resources — nothing extra to run. If you only changed frontend files,
`terraform apply` picks that up through the `filemd5()`-based `etag`.
There's no CDN cache to invalidate — changes are live as soon as the
`apply` finishes.

**9. Open it:**

```bash
terraform output frontend_url
```

Open that URL. See "Testing the deployed app" below for what to click
through.

## Wiring up CI/CD (M6)

`.github/workflows/deploy.yml` needs these set as GitHub **repo
variables** (Settings → Secrets and variables → Actions → **Variables**
tab — plain variables, not secrets; nothing sensitive is in them):

| Variable | Value |
|---|---|
| `AWS_REGION` | your `aws_region` |
| `ECR_REPOSITORY_URL` | `terraform output -raw ecr_repository_url` |
| `ECS_CLUSTER` | `terraform output -raw ecs_cluster_name` |
| `ECS_SERVICE` | `terraform output -raw ecs_service_name` |
| `APP_URL` | `terraform output -raw frontend_url` |

And these as GitHub **repo secrets** (same page, **Secrets** tab instead
— these values are real credentials, never put them in Variables):

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | `terraform output -raw github_actions_access_key_id` |
| `AWS_SECRET_ACCESS_KEY` | `terraform output -raw github_actions_secret_access_key` |

**Why a secret and not OIDC:** the OIDC role (`github_oidc.tf`) is fully
built and its trust policy has been verified correct against real GitHub
tokens, but `sts:AssumeRoleWithWebIdentity` fails with an unresolvable
`AccessDenied` on this account/sandbox, and AWS Support isn't reliably
available here to chase it further — see `NOTES.md` for the full
diagnosis. Using a scoped access key instead is a documented,
deliberate substitution, not the original design. Push to `main` and the
pipeline builds, tests, secret-scans, pushes to ECR, deploys, and smoke-tests
automatically. The Lambda thumbnailer image isn't wired into the pipeline
yet — repeat steps 6-7 by hand when `lambda/thumbnail/` changes.

## Testing the deployed app

1. Open `frontend_url`. You should land on the Dashboard (all zeros on a
   fresh deploy).
2. **New Ticket** → fill in the form → submit. You should be redirected to
   the ticket detail page.
3. On the detail page, change the **Status** dropdown — confirm the toast
   says it updated.
4. Add a comment and confirm it appears immediately below.
5. Upload an attachment (PNG/JPEG/GIF/PDF, under 5MB). The upload goes
   straight to S3, not through the API — check the Network tab in dev
   tools and you'll see the POST go to `*.s3.amazonaws.com`, not your API
   domain. A thumbnail should appear within a few seconds (the Lambda
   runs asynchronously); refresh the page if it doesn't show up
   immediately.
6. Go back to **Dashboard** and confirm the counts reflect what you just
   created.
7. `curl "$(terraform output -raw alb_dns_name)/api/health"` directly
   against the load balancer to confirm the ECS service itself is
   healthy — this is also literally what the frontend is calling, since
   frontend and API are separate origins now.
8. Open the CloudWatch dashboard: `terraform output cloudwatch_dashboard_url`.
9. Break something on purpose to test the alarms — e.g. temporarily set
   `desired_count = 0` and `terraform apply`, which should trip the
   unhealthy-targets alarm within a couple of minutes (confirm your SNS
   email subscription first, or you won't get notified). Set it back to
   `1` and re-apply afterwards.

## Destroying

```bash
terraform destroy
```

`skip_final_snapshot`/`deletion_protection = false` on RDS and
`recovery_window_in_days = 0` on the Secrets Manager secret are set
specifically so this leaves nothing billable behind (pass/fail gate 5) —
POC-only choices, not what you'd want in production. Do this whenever
you're done for the day — see the cost table above for why.

The `bootstrap/` stack (state bucket + lock table) is separate on
purpose — don't destroy it while the main stack's state still lives
there.

## What's still open

- The Lambda thumbnailer isn't part of the CI/CD pipeline — image updates
  are still a manual `docker build && docker push` + re-`apply` (steps
  6-7 above).
- `attachments_cors_allowed_origins` defaults to `["*"]` — tighten it to
  your `frontend_url` output once you have one, then re-apply.
- No CloudFront means no HTTPS on the app itself (S3 website endpoints
  and the ALB are both plain HTTP) — fine for a POC demo, but note it if
  a facilitator asks; §9's "HTTPS on a real domain" stretch goal would
  need CloudFront (or an ALB HTTPS listener + ACM cert) back in the
  picture.
- Auto-scaling and blue/green deployment are stretch goals (§9 of the
  brief) and aren't implemented.
- M8 (tagging pass, cost report, full teardown/rebuild rehearsal, smoke
  test suite, 20-user load sanity check) is a verification/process
  milestone more than an infrastructure one — everything here is already
  tagged via `default_tags` on the provider, but the rest of M8 (cost
  report, load test, checklist walkthrough) is on you and your pod.
