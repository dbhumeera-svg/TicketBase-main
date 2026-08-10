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
# CORS. var.attachments_cors_allowed_origins defaults to "*" for the POC;
# scope it to your frontend_url output once M4 is applied.
resource "aws_s3_bucket_cors_configuration" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  cors_rule {
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = var.attachments_cors_allowed_origins
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}
