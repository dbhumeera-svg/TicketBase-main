import logging
import os

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database import (
    Base,
    SessionLocal,
    engine,
    get_db,
)
from src.models import User
from src.routers import attachments, auth, notifications, tickets
from src.schemas import Role
from src.security import ENVIRONMENT, hash_password


logger = logging.getLogger("ticketdesk")


Base.metadata.create_all(
    bind=engine
)


def _seed_default_users() -> None:
    """Seeds starter admin/agent/user accounts so all three roles are
    ready to log in immediately. Admin exists without ever going through
    the public /auth/register endpoint (which deliberately refuses to
    create admins) - mirrors the reference project's DataInitializer,
    plus one demo USER account for convenience (a real deployment would
    instead have employees self-register as users via /auth/register).

    Only ever runs outside production - these are well-known, documented
    passwords, and creating them against a real production database
    would be a real backdoor, not a convenience."""

    db = SessionLocal()

    try:

        if db.query(User).filter(
            User.username == "admin"
        ).one_or_none() is None:

            db.add(
                User(
                    username="admin",
                    email="admin@ticketdesk.com",
                    password_hash=hash_password("Admin@1234"),
                    role=Role.ADMIN.value,
                )
            )

        if db.query(User).filter(
            User.username == "agent"
        ).one_or_none() is None:

            db.add(
                User(
                    username="agent",
                    email="agent@ticketdesk.com",
                    password_hash=hash_password("Agent@1234"),
                    role=Role.AGENT.value,
                )
            )

        if db.query(User).filter(
            User.username == "user"
        ).one_or_none() is None:

            db.add(
                User(
                    username="user",
                    email="user@ticketdesk.com",
                    password_hash=hash_password("User@1234"),
                    role=Role.USER.value,
                )
            )

        db.commit()

    finally:
        db.close()


if ENVIRONMENT == "prod":
    logger.info(
        "ENVIRONMENT=prod - skipping demo admin/agent/user seeding."
    )
else:
    _seed_default_users()


app = FastAPI(
    title="TicketDesk API",
    version="1.0.0",
    description=(
        "IT Support Ticket "
        "Management API"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "*"
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
):
    # Only reached for genuinely unexpected errors - every intentional
    # error path in the app already raises HTTPException, which FastAPI
    # handles separately and isn't affected by this. Logs the real error
    # server-side; the client only ever sees a generic message, never a
    # stack trace or exception internals.
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Everything lives under /api - a holdover from an earlier design where
# CloudFront routed "/api/*" to the ALB and everything else to the S3
# frontend on one domain. That's gone (see infra/README.md's "Why no
# CloudFront"); frontend and API are separate origins now, tied together
# via CORS_ORIGINS above instead of a shared domain. Keeping the prefix
# anyway costs nothing and leaves the door open to reintroducing a CDN
# later without an API path change.
api = APIRouter(prefix="/api")


@api.get("/")
def root():

    return {
        "message": (
            "TicketDesk API is running"
        )
    }


@api.get("/health")
def health_check():

    return {
        "status": "UP"
    }


@api.get("/health/database")
def database_health_check(
    db: Session = Depends(get_db),
):

    try:

        result = db.execute(
            text("SELECT 1")
        )

        if result.scalar() == 1:

            return {
                "status": "UP",
                "database": "CONNECTED",
            }

    except Exception:

        raise HTTPException(
            status_code=503,
            detail=(
                "Database is unavailable"
            ),
        )


api.include_router(auth.router)
api.include_router(tickets.router)
api.include_router(attachments.router)
api.include_router(notifications.router)

app.include_router(api)
