import os

# Must be set before `src.main` is imported anywhere, since it constructs a
# boto3 S3 client at module scope. Presigned URL generation is a local
# HMAC signing operation - it never calls AWS - so dummy credentials are
# enough to exercise the endpoints without real infrastructure.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("ATTACHMENTS_BUCKET", "ticketdesk-test-bucket")
os.environ.setdefault("DATABASE_URL", "sqlite:///./ticketdesk_test.db")
