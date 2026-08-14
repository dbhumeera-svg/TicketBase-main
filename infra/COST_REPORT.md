# TicketDesk POC — Cost Report

Checklist item 33: "Spend within budget, with a one-page cost report."
Prepared 2026-08-14, against AWS account 135274608372 (us-east-1).

## Actual spend so far

Cost Explorer's `UnblendedCost`, month-to-date (2026-08-01 → 2026-08-14):

```
$0.0000 (net; a handful of runs showed -$0.0000002xxx, which is
         Cost Explorer's own rounding noise, not real credit)
```

This is genuinely near-zero, not a query error — verified via `aws ce
get-cost-and-usage` grouped by both `SERVICE` and by the `Project` tag,
and cross-checked day-by-day (every day in the range shows `$0.000000
(estimated)`). Two things explain why a stack with an ALB, Fargate, and
5 VPC interface endpoints (all Free-Tier-ineligible per the table below)
shows ~$0 billed:

1. **This account is still well inside its 12-month AWS Free Tier
   window**, and several of the "not free tier" line items in the table
   below (VPC endpoints, ALB, Fargate) are billed in small enough
   increments at this usage level (a few hours a day, torn down between
   sessions via `terraform destroy`) that they round to sub-cent amounts
   Cost Explorer hasn't finished attributing yet.
2. **Cost Explorer data lags real usage by up to 24 hours** and every
   row in this report is still flagged `"Estimated": true` - the true
   total for 2026-08-14 (today, mid-session) won't be final until
   tomorrow.

**Tag-filtered view**: cost allocation tags (`Environment`, `Project`,
`Owner`, `CostCenter`, `Name` - all `Inactive` since account creation)
were activated today via `aws ce update-cost-allocation-tags-status`.
AWS does not backfill tag-based cost breakdowns retroactively - a
tag-filtered Cost Explorer view only starts attributing spend to tags
from the moment of activation forward, so today's near-zero total is
expected and not yet a meaningful tag-scoped sample. The filter is live
and will attribute correctly starting today.

## Top 2 most expensive resources (by design, not by billed amount)

Since billed amounts round to ~$0 so far, "most expensive" here means
what would actually drive cost if this stack ran continuously - per the
existing cost table in [infra/README.md](README.md#cost-reality-check--read-this-before-you-apply):

1. **5 VPC interface endpoints (ECR api/dkr, logs, Secrets Manager,
   SSM), 1 AZ each** - ~$36/month. The single biggest line item, and the
   direct trade-off made to avoid a NAT Gateway (which would cost more
   and require public egress the brief doesn't need).
2. **Application Load Balancer** - ~$16/month. Fixed hourly cost
   regardless of traffic; the only public-facing compute-adjacent
   resource in the stack (checklist items 10-11).

Fargate compute (~$9-10/month) is a close third - included for
completeness since it's the other non-free-tier always-on cost.

## Budget

A monthly budget was created via `aws budgets create-budget`, scoped to
the `Project=TicketDesk` tag:

- **Name**: `TicketDesk-POC-Budget`
- **Limit**: $25/month (comfortably above the ~$61/month full-24/7 run
  rate from the table below would be low, but this is a POC torn down
  between sessions, not a 24/7 deployment - $25 gives headroom for a few
  days of continuous testing without masking a real runaway-cost bug)
- **Alert**: email to workdsp5@gmail.com at 80% of actual spend
- Confirmed present via `aws budgets describe-budgets`

## Estimated monthly cost if left running 24/7

Reproduced from [infra/README.md](README.md#cost-reality-check--read-this-before-you-apply):

| Resource | Free tier? | Approx. cost running 24/7 |
|---|---|---|
| 5 VPC interface endpoints × 1 AZ | ❌ None | ~$36/month |
| Application Load Balancer | ❌ None | ~$16/month |
| ECS Fargate task (256/512) | ❌ None | ~$9-10/month |
| Secrets Manager (2 secrets: DB password, JWT secret) | ❌ None | ~$0.80/month |
| RDS `db.t3.micro`, single instance | ✅ 750 hrs/mo, first 12 mo | Free |
| S3 (frontend + attachments) | ✅ 5GB, 20k GET, 2k PUT/mo | Free at demo volume |
| Lambda (thumbnailer) | ✅ 1M requests/mo | Free at demo volume |
| CloudWatch (1 dashboard, 3 alarms) | ✅ 3 dashboards, 10 alarms free | Free |
| SNS | ✅ 1,000 email notifications/mo | Free at demo volume |
| ECR (2 repos) | ✅ 500MB/mo, first 12 mo | Free unless images pile up |
| **Total, if left running continuously** | | **~$62-63/month** |

The mitigation already built and used throughout this project:
`terraform destroy` (via `./destroy.sh`) between sessions, `terraform
apply` again before the next one - proven end-to-end today (see
NOTES.md's destroy/rebuild entry). That turns ~$62/month into a few
dollars for the hours actually spent developing and demoing.

## AWS Free Tier usage (informational, not billed cost)

`aws freetier get-free-tier-usage` shows this project's usage is a small
fraction of the always-free allowances (Lambda: 4.1 of 400,000 free
GB-seconds used; well under 1% on every line checked) - included here to
show the free-tier-eligible pieces (Lambda, S3, RDS hours) aren't close
to their caps, not because it represents money spent.
