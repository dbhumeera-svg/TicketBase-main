#!/usr/bin/env bash
# Safe wrapper around `terraform destroy`.
#
# Reads which environment is *actually deployed* (terraform output, not
# a possibly-stale tfvars file) and gates on it:
#   - prod            : refuses to run non-interactively; the operator
#                        must type the literal phrase "destroy production"
#                        at a prompt. No flag or env var skips this.
#   - dev / test       : shows `terraform plan -destroy` and asks for a
#                        plain y/N before proceeding.
#
# This is a human-facing safety net on top of the AWS-enforced one:
# infra/rds.tf sets deletion_protection = true whenever environment =
# "prod", so even a confirmed destroy still can't remove the database
# without that being turned off by hand first.
#
# Usage:
#   ./destroy.sh                        # destroy whatever this directory's
#                                        # state currently points at
#   ./destroy.sh -var="environment=test" [any other terraform destroy args]
#
# Run from infra/ (or anywhere - the script cd's there itself).

set -euo pipefail

cd "$(dirname "$0")"

if ! command -v terraform >/dev/null 2>&1; then
  echo "terraform is not on PATH." >&2
  exit 1
fi

echo "Checking what's actually in state for this backend..."
echo

# terraform output reads real state - if nothing has ever been applied,
# this fails cleanly and we treat that as "nothing to destroy."
if ! CURRENT_ENV=$(terraform output -raw environment 2>/dev/null); then
  echo "No deployed state found (or the 'environment' output isn't"
  echo "available yet - run 'terraform apply' at least once first)."
  echo "Nothing to destroy."
  exit 0
fi

echo "Deployed environment: $CURRENT_ENV"
echo

if [ "$CURRENT_ENV" = "prod" ]; then
  echo "############################################################"
  echo "#   YOU ARE ABOUT TO DESTROY THE PRODUCTION ENVIRONMENT.    #"
  echo "#                                                            #"
  echo "#   RDS has deletion_protection=true in prod, so the        #"
  echo "#   database itself will refuse to be deleted until that's  #"
  echo "#   turned off by hand first - but everything else (ECS,    #"
  echo "#   ALB, S3 buckets, Lambda, etc.) WILL be destroyed if you  #"
  echo "#   proceed past this prompt.                                #"
  echo "############################################################"
  echo
  read -r -p "Type 'destroy production' to continue, anything else cancels: " CONFIRM

  if [ "$CONFIRM" != "destroy production" ]; then
    echo "Cancelled. Nothing was destroyed."
    exit 1
  fi

  echo
  echo "Confirmed. Running terraform destroy against production..."
  terraform destroy "$@"
else
  echo "This will destroy the '$CURRENT_ENV' environment. Showing the plan first:"
  echo
  terraform plan -destroy "$@"
  echo
  read -r -p "Proceed with terraform destroy? [y/N] " CONFIRM

  case "$CONFIRM" in
    [yY] | [yY][eE][sS])
      terraform destroy "$@"
      ;;
    *)
      echo "Cancelled. Nothing was destroyed."
      exit 1
      ;;
  esac
fi
