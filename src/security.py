import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import User
from src.schemas import Role


# Matches infra/variables.tf's var.environment convention exactly
# (dev/test/prod) - infra/ecs.tf injects this verbatim as ENVIRONMENT, so
# using any other word here (e.g. "production") would silently defeat
# both checks below in a real deploy.
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

_JWT_SECRET_ENV = os.getenv("JWT_SECRET")

if ENVIRONMENT == "prod" and not _JWT_SECRET_ENV:
    # A production deploy always injects this from Secrets Manager
    # (infra/ecs.tf) - reaching here means that's missing, which is a
    # deploy misconfiguration worth failing loudly on rather than
    # silently running production with a throwaway secret.
    raise RuntimeError(
        "JWT_SECRET must be set when ENVIRONMENT=prod."
    )

# No JWT_SECRET configured (typical for local dev): mint a random secret
# once per process instead of falling back to a fixed string. Every
# restart then invalidates every previously-issued token - the frontend's
# api() helper already clears localStorage and redirects to #/login on a
# 401, so this is what actually logs a user out when the dev server
# restarts. A real JWT_SECRET (prod, or anyone who sets one locally)
# stays stable across restarts, which is the correct behavior there.
JWT_SECRET = _JWT_SECRET_ENV or secrets.token_hex(32)

JWT_ALGORITHM = "HS256"

JWT_EXPIRE_MINUTES = 24 * 60

# tokenUrl only affects the Swagger "Authorize" UI - the token is a plain
# self-contained JWT, not an OAuth2 flow.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_error

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        raise credentials_error

    user_id = payload.get("user_id")

    if user_id is None:
        raise credentials_error

    user = db.get(User, user_id)

    if user is None:
        raise credentials_error

    return user


def require_roles(*roles: Role):
    """FastAPI dependency factory: 403s unless current_user.role is one
    of `roles`. Usage: Depends(require_roles(Role.ADMIN))."""

    allowed = {role.value for role in roles}

    def _dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:

        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You do not have permission to perform this action."
                ),
            )

        return current_user

    return _dependency
