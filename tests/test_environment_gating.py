"""Covers behavior that only happens at process startup (demo-user
seeding, the JWT_SECRET fail-fast check) - these need a real fresh
Python process per case, since the module-level code in src/main.py and
src/security.py only ever runs once per interpreter. See src/main.py's
_seed_default_users gating and src/security.py's ENVIRONMENT/JWT_SECRET
handling."""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run(env_overrides, code):
    env = os.environ.copy()
    env.update(env_overrides)

    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_demo_users_not_seeded_in_prod(tmp_path):
    db_file = tmp_path / "prod_check.db"

    result = _run(
        {
            "ENVIRONMENT": "prod",
            "JWT_SECRET": "a-real-production-secret",
            "DATABASE_URL": f"sqlite:///{db_file}",
            "ATTACHMENTS_BUCKET": "",
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
        (
            "from src.main import SessionLocal\n"
            "from src.models import User\n"
            "db = SessionLocal()\n"
            "print('USER_COUNT=' + str(db.query(User).count()))\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert "USER_COUNT=0" in result.stdout


def test_demo_users_seeded_outside_prod(tmp_path):
    db_file = tmp_path / "dev_check.db"

    result = _run(
        {
            "ENVIRONMENT": "dev",
            "DATABASE_URL": f"sqlite:///{db_file}",
            "ATTACHMENTS_BUCKET": "",
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
        (
            "from src.main import SessionLocal\n"
            "from src.models import User\n"
            "db = SessionLocal()\n"
            "usernames = sorted(u.username for u in db.query(User).all())\n"
            "print('USERS=' + ','.join(usernames))\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert "USERS=admin,agent,user" in result.stdout


def test_prod_without_jwt_secret_fails_fast(tmp_path):
    db_file = tmp_path / "no_secret_check.db"

    result = _run(
        {
            "ENVIRONMENT": "prod",
            "JWT_SECRET": "",
            "DATABASE_URL": f"sqlite:///{db_file}",
            "ATTACHMENTS_BUCKET": "",
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_DEFAULT_REGION": "us-east-1",
        },
        "import src.main\n",
    )

    assert result.returncode != 0
    assert "JWT_SECRET must be set when ENVIRONMENT=prod" in result.stderr
