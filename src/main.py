import os
import uuid
from pathlib import Path
from typing import Optional

import boto3
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from src.database import (
    Base,
    engine,
    get_db,
)
from src.models import (
    Attachment,
    Comment,
    Ticket,
)
from src.schemas import (
    AttachmentPresignRequest,
    AttachmentPresignResponse,
    AttachmentResponse,
    CommentCreate,
    CommentResponse,
    DashboardSummary,
    TicketCategory,
    TicketCreate,
    TicketPriority,
    TicketResponse,
    TicketStatus,
    TicketStatusUpdate,
)


Base.metadata.create_all(
    bind=engine
)


ATTACHMENTS_BUCKET = os.getenv("ATTACHMENTS_BUCKET")

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

ALLOWED_ATTACHMENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "application/pdf",
}

PRESIGN_UPLOAD_EXPIRY = 300
PRESIGN_DOWNLOAD_EXPIRY = 3600

s3_client = boto3.client("s3")


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

# Everything lives under /api - a holdover from an earlier design where
# CloudFront routed "/api/*" to the ALB and everything else to the S3
# frontend on one domain. That's gone (see infra/README.md's "Why no
# CloudFront"); frontend and API are separate origins now, tied together
# via CORS_ORIGINS above instead of a shared domain. Keeping the prefix
# anyway costs nothing and leaves the door open to reintroducing a CDN
# later without an API path change.
api = APIRouter(prefix="/api")


def _thumbnail_key(original_key: str) -> str:
    suffix = original_key.removeprefix("attachments/")
    return f"thumbnails/{suffix}.png"


def _presigned_get(key: str) -> str:
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": ATTACHMENTS_BUCKET, "Key": key},
        ExpiresIn=PRESIGN_DOWNLOAD_EXPIRY,
    )


def _attachment_response(attachment: Attachment) -> AttachmentResponse:

    return AttachmentResponse(
        id=attachment.id,
        ticket_id=attachment.ticket_id,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        created_at=attachment.created_at,
        download_url=_presigned_get(attachment.s3_key),
        thumbnail_url=_presigned_get(
            _thumbnail_key(attachment.s3_key)
        ),
    )


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


@api.get(
    "/dashboard",
    response_model=DashboardSummary,
)
def get_dashboard_summary(
    db: Session = Depends(get_db),
):

    total = db.query(
        func.count(Ticket.id)
    ).scalar()

    status_rows = (
        db.query(
            Ticket.status,
            func.count(Ticket.id),
        )
        .group_by(Ticket.status)
        .all()
    )

    priority_rows = (
        db.query(
            Ticket.priority,
            func.count(Ticket.id),
        )
        .group_by(Ticket.priority)
        .all()
    )

    by_status = {
        status.value: 0
        for status in TicketStatus
    }
    by_status.update(dict(status_rows))

    by_priority = {
        priority.value: 0
        for priority in TicketPriority
    }
    by_priority.update(dict(priority_rows))

    return DashboardSummary(
        total_tickets=total or 0,
        by_status=by_status,
        by_priority=by_priority,
    )


@api.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=201,
)
def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
):

    new_ticket = Ticket(
        title=ticket.title,
        description=ticket.description,
        category=ticket.category.value,
        priority=ticket.priority.value,
        status=TicketStatus.OPEN.value,
    )

    db.add(new_ticket)

    db.commit()

    db.refresh(new_ticket)

    return new_ticket


@api.get(
    "/tickets",
    response_model=list[TicketResponse],
)
def get_all_tickets(
    status: Optional[TicketStatus] = Query(
        default=None
    ),
    priority: Optional[TicketPriority] = Query(
        default=None
    ),
    category: Optional[TicketCategory] = Query(
        default=None
    ),
    db: Session = Depends(get_db),
):

    query = db.query(Ticket)

    if status is not None:

        query = query.filter(
            Ticket.status == status.value
        )

    if priority is not None:

        query = query.filter(
            Ticket.priority == priority.value
        )

    if category is not None:

        query = query.filter(
            Ticket.category == category.value
        )

    return query.order_by(
        Ticket.id
    ).all()


@api.get(
    "/tickets/{ticket_id}",
    response_model=TicketResponse,
)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
):

    ticket = db.get(
        Ticket,
        ticket_id,
    )

    if ticket is None:

        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    return ticket


@api.patch(
    "/tickets/{ticket_id}/status",
    response_model=TicketResponse,
)
def update_ticket_status(
    ticket_id: int,
    update: TicketStatusUpdate,
    db: Session = Depends(get_db),
):

    ticket = db.get(
        Ticket,
        ticket_id,
    )

    if ticket is None:

        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    ticket.status = update.status.value

    db.commit()

    db.refresh(ticket)

    return ticket


@api.delete(
    "/tickets/{ticket_id}",
)
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
):

    ticket = db.get(
        Ticket,
        ticket_id,
    )

    if ticket is None:

        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    db.delete(ticket)

    db.commit()

    return {
        "message": (
            "Ticket deleted successfully"
        )
    }


@api.post(
    "/tickets/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
def add_comment(
    ticket_id: int,
    comment: CommentCreate,
    db: Session = Depends(get_db),
):

    ticket = db.get(
        Ticket,
        ticket_id,
    )

    if ticket is None:

        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    new_comment = Comment(
        ticket_id=ticket_id,
        author=comment.author,
        message=comment.message,
    )

    db.add(new_comment)

    db.commit()

    db.refresh(new_comment)

    return new_comment


@api.get(
    "/tickets/{ticket_id}/comments",
    response_model=list[CommentResponse],
)
def get_ticket_comments(
    ticket_id: int,
    db: Session = Depends(get_db),
):

    ticket = db.get(
        Ticket,
        ticket_id,
    )

    if ticket is None:

        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    return (
        db.query(Comment)
        .filter(
            Comment.ticket_id == ticket_id
        )
        .order_by(
            Comment.id
        )
        .all()
    )


@api.post(
    "/tickets/{ticket_id}/attachments/presign",
    response_model=AttachmentPresignResponse,
    status_code=201,
)
def presign_attachment_upload(
    ticket_id: int,
    request: AttachmentPresignRequest,
    db: Session = Depends(get_db),
):
    """Issue a presigned POST so the browser uploads straight to S3 -
    the API never sees the file bytes (checklist item 23)."""

    if not ATTACHMENTS_BUCKET:

        raise HTTPException(
            status_code=503,
            detail=(
                "ATTACHMENTS_BUCKET is not configured on the server."
            ),
        )

    ticket = db.get(
        Ticket,
        ticket_id,
    )

    if ticket is None:

        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    if request.content_type not in ALLOWED_ATTACHMENT_TYPES:

        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported file type. "
                "Allowed: PNG, JPEG, GIF, PDF."
            ),
        )

    existing = (
        db.query(Attachment)
        .filter(
            Attachment.ticket_id == ticket_id
        )
        .one_or_none()
    )

    if existing is not None:

        # The old object (and its thumbnail, if generated) is left in S3
        # rather than deleted synchronously here - deleting is a real
        # network call, and this request shouldn't have to wait on S3 (or
        # fail) just to replace a DB row. It's an orphaned object at that
        # point; a periodic cleanup job comparing the bucket against the
        # DB is the correct fix and is out of scope for this POC.
        db.delete(existing)

        db.flush()

    safe_name = Path(request.filename).name.replace(" ", "_")

    s3_key = (
        f"attachments/{ticket_id}/{uuid.uuid4().hex}-{safe_name}"
    )

    attachment = Attachment(
        ticket_id=ticket_id,
        original_filename=safe_name,
        s3_key=s3_key,
        content_type=request.content_type,
    )

    db.add(attachment)

    db.commit()

    db.refresh(attachment)

    presigned = s3_client.generate_presigned_post(
        Bucket=ATTACHMENTS_BUCKET,
        Key=s3_key,
        Fields={"Content-Type": request.content_type},
        Conditions=[
            {"Content-Type": request.content_type},
            ["content-length-range", 1, MAX_ATTACHMENT_BYTES],
        ],
        ExpiresIn=PRESIGN_UPLOAD_EXPIRY,
    )

    return AttachmentPresignResponse(
        attachment_id=attachment.id,
        upload_url=presigned["url"],
        upload_fields=presigned["fields"],
    )


@api.get(
    "/tickets/{ticket_id}/attachments",
    response_model=Optional[AttachmentResponse],
)
def get_ticket_attachment(
    ticket_id: int,
    db: Session = Depends(get_db),
):

    ticket = db.get(
        Ticket,
        ticket_id,
    )

    if ticket is None:

        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    attachment = (
        db.query(Attachment)
        .filter(
            Attachment.ticket_id == ticket_id
        )
        .one_or_none()
    )

    if attachment is None:

        return None

    return _attachment_response(attachment)


app.include_router(api)
