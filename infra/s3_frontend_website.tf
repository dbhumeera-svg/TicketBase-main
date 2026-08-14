# M4, Free Tier-safe variant: S3 static website hosting instead of
# CloudFront. CloudFront's own free tier (1TB/10M requests per month) is
# in practice unlimited for a class demo, but S3 website hosting has zero
# moving parts to misconfigure into a surprise bill, and sidesteps the
# "account must be verified before you can add CloudFront resources"
# block new/free-tier accounts sometimes hit.
#
# Trade-off, stated plainly rather than hidden: S3 website hosting has no
# private-origin mode, so this bucket has to allow public, read-only
# access to do its job - it diverges from checklist item 22 ("S3 bucket
# is not public"). It holds only static HTML/CSS/JS with zero secrets or
# user data, so the actual risk is nil; worth one honest line in your
# NOTES.md rather than silently deviating. Swap back to cloudfront.tf's
# approach (kept in git history) once your account's CloudFront
# verification clears, if you want the checklist item back to the letter.
#
# Both this and the ALB are plain HTTP - S3 website endpoints don't
# support HTTPS directly (that's normally CloudFront's job), and the ALB
# has no ACM cert either, so keeping both on HTTP avoids a mixed-content
# browser error rather than introducing one.

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.name_prefix}-frontend"

  # Without this, `terraform destroy` fails with BucketNotEmpty once the
  # static site files are in there - a POC bucket has no retention
  # requirement that would argue for the safer default.
  force_destroy = true

  tags = { Name = "${var.name_prefix}-frontend" }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  # ACLs stay blocked - public access here is deliberate and scoped
  # through the bucket policy below, not left open to accidental
  # ACL-based exposure.
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  # The frontend uses hash-based routing (#/tickets/...), so the fragment
  # never reaches S3 - every real request is for index.html, app.js,
  # styles.css or config.js. No error-document SPA fallback needed.
}

data "aws_iam_policy_document" "frontend_bucket" {
  statement {
    sid       = "PublicReadOnly"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket.json

  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

locals {
  frontend_mime_types = {
    ".html" = "text/html"
    ".js"   = "application/javascript"
    ".css"  = "text/css"
  }

  # config.js is generated here rather than uploaded from frontend/ as-is:
  # the checked-in copy points at http://localhost:8000 for local dev
  # (see frontend/config.js), but the deployed copy needs the real ALB
  # DNS name - frontend and API are on different origins now (no
  # CloudFront to put them under one domain), so this relies on the
  # backend's CORS_ORIGINS below rather than same-origin requests.
  frontend_files = {
    "index.html" = { source = "${path.module}/../frontend/index.html" }
    "app.js"     = { source = "${path.module}/../frontend/app.js" }
    "styles.css" = { source = "${path.module}/../frontend/styles.css" }
  }
}

resource "aws_s3_object" "frontend_files" {
  for_each = local.frontend_files

  bucket       = aws_s3_bucket.frontend.id
  key          = each.key
  source       = each.value.source
  etag         = filemd5(each.value.source)
  content_type = lookup(local.frontend_mime_types, regex("\\.[^.]+$", each.key), "application/octet-stream")
}

resource "aws_s3_object" "frontend_config" {
  bucket = aws_s3_bucket.frontend.id
  key    = "config.js"
  content = format(
    "window.TICKETDESK_DEFAULT_API_BASE = \"http://%s\";\n",
    aws_lb.main.dns_name
  )
  content_type = "application/javascript"
  etag = md5(format(
    "window.TICKETDESK_DEFAULT_API_BASE = \"http://%s\";\n",
    aws_lb.main.dns_name
  ))
}
