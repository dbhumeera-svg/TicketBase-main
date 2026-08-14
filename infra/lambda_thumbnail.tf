# Container-image Lambda - see lambda/thumbnail/Dockerfile for why.
resource "aws_ecr_repository" "lambda_thumbnail" {
  name                 = "${var.name_prefix}-thumbnail-lambda"
  image_tag_mutability = "IMMUTABLE"

  # Without this, `terraform destroy` fails once CI has pushed even one
  # image - a POC registry has no retention requirement that would argue
  # for the safer default.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = { Name = "${var.name_prefix}-thumbnail-lambda" }
}

resource "aws_cloudwatch_log_group" "lambda_thumbnail" {
  name              = "/aws/lambda/${var.name_prefix}-thumbnail"
  retention_in_days = 14

  tags = { Name = "${var.name_prefix}-thumbnail-logs" }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_thumbnail" {
  name               = "${var.name_prefix}-thumbnail-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = { Name = "${var.name_prefix}-thumbnail-lambda-role" }
}

# Scoped to exactly the two prefixes this function touches - read the
# original, write the thumbnail - plus its own log stream. No "*" resource.
data "aws_iam_policy_document" "lambda_thumbnail_permissions" {
  statement {
    sid       = "ReadOriginal"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.attachments.arn}/attachments/*"]
  }

  statement {
    sid       = "WriteThumbnail"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.attachments.arn}/thumbnails/*"]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.lambda_thumbnail.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda_thumbnail" {
  name   = "${var.name_prefix}-thumbnail-lambda-policy"
  role   = aws_iam_role.lambda_thumbnail.id
  policy = data.aws_iam_policy_document.lambda_thumbnail_permissions.json
}

resource "aws_lambda_function" "thumbnail" {
  function_name = "${var.name_prefix}-thumbnail"
  role          = aws_iam_role.lambda_thumbnail.arn
  package_type  = "Image"
  image_uri     = var.lambda_image
  timeout       = 30
  memory_size   = 512

  depends_on = [
    aws_iam_role_policy.lambda_thumbnail,
    aws_cloudwatch_log_group.lambda_thumbnail,
  ]

  tags = { Name = "${var.name_prefix}-thumbnail" }
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.thumbnail.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.attachments.arn
}

# Only the attachments/ prefix triggers this - the thumbnails/ prefix it
# writes to is deliberately excluded, or every thumbnail write would
# re-trigger the function against itself.
resource "aws_s3_bucket_notification" "attachments" {
  bucket = aws_s3_bucket.attachments.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.thumbnail.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "attachments/"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
