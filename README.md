# TicketDesk

TicketDesk is an IT Support Ticket Management Platform: FastAPI +
SQLAlchemy backend, a static HTML/CSS/JS frontend, and a Terraform-defined
AWS deployment (ECS Fargate, RDS, S3, Lambda, Secrets Manager, CloudWatch,
GitHub Actions CI/CD).

## Features

- Create support tickets (title, description, category, priority)
- View all tickets, view a ticket by ID
- Update ticket status (OPEN → IN_PROGRESS → RESOLVED → CLOSED)
- Delete tickets
- Add threaded ticket comments
- Filter tickets by priority, category, and status
- Dashboard summary: total tickets, counts by status, counts by priority
- One file attachment per ticket (PNG/JPEG/GIF/PDF, up to 5MB), uploaded
  directly to S3 via a presigned URL, with an async Lambda-generated
  thumbnail
- Application health check and database health check

All backend routes live under `/api` (e.g. `/api/tickets`,
`/api/health`). Deployed, the frontend (S3 static website) and API (ALB)
are on separate origins, tied together with CORS — see "Why no
CloudFront" below.

## Running locally

Easiest path — one command starts both and opens the browser:

```bash
pip install -r requirements.txt
python run.py
```

Or run each piece by hand:

```bash
# Backend
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./ticketdesk.db   # or a Postgres URL
uvicorn src.main:app --reload --port 8000

# Frontend (static, no build step)
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500`; the sidebar's API base URL defaults to
`http://localhost:8000` (see `frontend/config.js`). The backend enables
CORS for all origins by default locally (override with `CORS_ORIGINS`).

**Attachments locally:** the presigned-upload flow calls S3 for real, so
it needs `ATTACHMENTS_BUCKET` set to a real bucket and real AWS
credentials available (`aws configure`, or `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` in your environment).
Every other feature works with zero AWS setup.

## Testing

Automated API tests (pytest) cover tickets, comments, health checks, the
dashboard, and the presigned-attachment flow (S3 calls are never actually
made in tests — presigned URL generation is a local signing operation, so
dummy credentials are enough; see `tests/conftest.py`).

```bash
pip install -r requirements.txt
python -m pytest -v
```

24 tests, all passing locally and in CI.

## CI/CD

`.github/workflows/deploy.yml`: on every push to `main` —
test → secret scan → build → push to ECR → deploy to ECS → smoke test.
Any failing step blocks the ones after it. Authenticates to AWS via
GitHub OIDC federation (no access keys in GitHub). Setup instructions
(which repo variables to set, where the values come from) are in
[infra/README.md](infra/README.md#wiring-up-cicd-m6).

## Infrastructure as Code

Everything is defined in Terraform under [infra/](infra/) —
[infra/README.md](infra/README.md) has the full bootstrap → deploy →
test → destroy walkthrough, **plus a per-service cost table — read that
before you leave anything running.**

```
Browser ──► S3 static website (frontend)
Browser ──► ALB ──► ECS Fargate ──► RDS (private)
                              └──► S3 attachments ──► Lambda (thumbnail)
```

### Why no CloudFront

The brief's diagram puts CloudFront in front of the S3 frontend. This
deployment deliberately doesn't:

- CloudFront on a new/free-tier AWS account can require manual account
  verification before it'll create a distribution at all (an
  `AccessDenied` error we hit directly) — a multi-day support-ticket
  dependency that isn't worth having on the critical path.
- CloudFront's own Free Tier is generous enough that it wasn't really the
  cost risk anyway — the VPC interface endpoints, the ALB, and Fargate
  are what actually bill continuously (see the cost table in
  [infra/README.md](infra/README.md)). Removing CloudFront doesn't move
  the needle much on cost; it does remove a dependency and a point of
  failure.

Trade-off, stated rather than hidden: the frontend S3 bucket has to be
public (read-only, static assets only, no secrets) for website hosting to
work without CloudFront in front — a deviation from checklist item 22
worth a line in your NOTES for demo day. `s3_frontend_website.tf` has the
full reasoning.

Covers:

- VPC — 2 public + 2 private subnets across 2 AZs, no NAT Gateway (VPC
  interface/gateway endpoints instead, deliberately in one AZ to halve
  their cost — see infra/README.md)
- ALB (public) → ECS Fargate (private); security groups reference each
  other, not `0.0.0.0/0`, except the ALB's public listener
- RDS PostgreSQL — private, encrypted, automated backups, not publicly
  accessible
- DB password in Secrets Manager; everything else (host, port, name,
  user, CORS origins, attachments bucket) in Parameter Store, read by the
  ECS task at container start via a scoped IAM execution role
- S3 static website for the frontend; CORS-scoped to the ALB for API
  calls, since it's a separate origin
- S3 attachments bucket + a container-image Lambda that generates
  thumbnails on upload
- CloudWatch dashboard (requests, errors, latency, CPU/memory, DB
  connections) + 3 alarms (5xx errors, unhealthy targets, high DB CPU)
  wired to an SNS topic
- GitHub OIDC provider + a deploy role scoped to exactly what the
  pipeline does (no `"*"` on `"*"`)
- ECR (image scanning on, immutable tags) + CloudWatch log groups

Not automated as code:

- Auto-scaling, HTTPS on a real domain, blue/green deployment — stretch
  goals (§9 of the brief), not implemented (HTTPS specifically would need
  CloudFront or an ALB HTTPS listener back in the picture)
- Updating the Lambda thumbnailer image isn't wired into
  `deploy.yml` yet — still a manual step (documented in
  [infra/README.md](infra/README.md))
- M8's cost report, load sanity check, and full checklist walkthrough are
  verification steps for you and your pod to run against a real deploy,
  not something Terraform produces

## Status against real AWS

This has been applied against a real account — not just written and
locally checked. One real bug turned up and got fixed along the way: the
ECS service had no explicit dependency on the execution role's IAM
policies or the VPC endpoints, so Terraform could (and did) create the
service before either was actually ready, causing
`CannotPullContainerError`. `infra/ecs.tf`'s `depends_on` now makes that
ordering explicit. If something else doesn't match reality on your next
apply, that's expected — check the Terraform error or the ECS task's
stopped-task reason before changing anything (per the brief's own
advice), and it's usually faster to resolve than it looks.
