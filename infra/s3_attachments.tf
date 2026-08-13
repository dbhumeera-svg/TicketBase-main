resource "aws_s3_bucket" "attachments" {
  bucket = "${var.name_prefix}-attachments"

  tags = { Name = "${var.name_prefix}-attachments" }
}

resource "aws_s3_bucket_public_access_block" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  versioning_configuration {
    status = "Enabled"
  }
}

# The browser uploads (presigned POST) and views/downloads (presigned GET)
# objects directly, from the frontend's S3 website origin - a
# cross-origin request from this bucket's point of view, so it needs
# CORS. The frontend bucket's website_configuration is a resource in this
# same root module, so the real origin is known at apply time - same
# trick aws_ssm_parameter.cors_origins already uses - which avoids ever
# needing a "*" default or a two-step apply to tighten it after the fact.
# var.attachments_cors_allowed_origins is only for extra origins (e.g. a
# custom domain later); it's empty by default.
resource "aws_s3_bucket_cors_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  cors_rule {
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = concat(
      ["http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"],
      var.attachments_cors_allowed_origins,
    )
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}
