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
os.environ.setdefault("JWT_SECRET", "test-only-secret")

from src.database import Base, engine  # noqa: E402
from src.main import _seed_default_users  # noqa: E402


DEFAULT_PASSWORD = "Password@123"


def reset_db():
    """Drops and recreates every table, then reseeds the default
    admin/agent accounts - mirrors what happens on a real app restart
    against an empty database. Call this from each test module's
    setup_function instead of the drop_all/create_all pair directly."""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_default_users()


def register_user(client, username, role=None, password=DEFAULT_PASSWORD):
    """Registers a user (USER by default, or AGENT) through the public
    endpoint and returns the parsed UserResponse body."""

    payload = {
        "username": username,
        "email": f"{username}@example.com",
        "password": password,
    }

    if role is not None:
        payload["role"] = role

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 201, response.text

    return response.json()


def login(client, username, password=DEFAULT_PASSWORD):
    """Logs in and returns the raw JWT string."""

    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )

    assert response.status_code == 200, response.text

    return response.json()["token"]


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, username, role=None, password=DEFAULT_PASSWORD):
    """Convenience wrapper: registers (if not already seeded) then logs
    in, returning an Authorization header dict ready to pass to the
    TestClient."""

    register_user(client, username, role=role, password=password)

    return auth_header(login(client, username, password=password))
