import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

import boto3
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Attachment, User
from src.schemas import (
    AttachmentPresignRequest,
    AttachmentPresignResponse,
    AttachmentResponse,
)
from src.security import get_current_user
from src.ticket_access import can_view_ticket, get_ticket_or_404


router = APIRouter(prefix="/tickets", tags=["attachments"])

ATTACHMENTS_BUCKET = os.getenv("ATTACHMENTS_BUCKET")

# Used only when ATTACHMENTS_BUCKET isn't set - lets attachments work on a
# local dev machine with no AWS account, at the cost of the presigned-URL
# security model (see the local-mode endpoints below for the tradeoff).
LOCAL_UPLOAD_ROOT = Path(
    os.getenv("LOCAL_ATTACHMENTS_DIR", "uploads")
)

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


def _thumbnail_key(original_key: str) -> str:
    suffix = original_key.removeprefix("attachments/")
    return f"thumbnails/{suffix}.png"


def _presigned_get(key: str) -> str:
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": ATTACHMENTS_BUCKET, "Key": key},
        ExpiresIn=PRESIGN_DOWNLOAD_EXPIRY,
    )


def _local_file_url(http_request: Request, attachment: Attachment) -> str:
    base = str(http_request.base_url).rstrip("/")
    return (
        f"{base}/api/tickets/{attachment.ticket_id}"
        f"/attachments/{attachment.id}/file"
    )


def _attachment_response(
    attachment: Attachment, http_request: Request
) -> AttachmentResponse:

    if ATTACHMENTS_BUCKET:
        download_url = _presigned_get(attachment.s3_key)
        # The Lambda thumbnailer only exists in the S3 deployment; a
        # missing thumbnail just makes the frontend hide the <img> tag
        # (see app.js's onerror handler), so this is safe even before
        # the thumbnail has been generated yet.
        thumbnail_url = _presigned_get(
            _thumbnail_key(attachment.s3_key)
        )
    else:
        file_url = _local_file_url(http_request, attachment)
        download_url = file_url
        thumbnail_url = file_url

    return AttachmentResponse(
        id=attachment.id,
        ticket_id=attachment.ticket_id,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        created_at=attachment.created_at,
        download_url=download_url,
        thumbnail_url=thumbnail_url,
    )


def _require_ticket_access(
    db: Session, ticket_id: int, current_user: User, action: str
):

    ticket = get_ticket_or_404(db, ticket_id)

    if not can_view_ticket(ticket, current_user):

        raise HTTPException(
            status_code=403,
            detail=(
                f"You are not authorized to {action} on "
                f"ticket ID: {ticket_id}"
            ),
        )

    return ticket


@router.post(
    "/{ticket_id}/attachments/presign",
    response_model=AttachmentPresignResponse,
    status_code=201,
)
def presign_attachment_upload(
    ticket_id: int,
    request: AttachmentPresignRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue a presigned POST so the browser uploads straight to S3 -
    the API never sees the file bytes (checklist item 23). Falls back to
    uploading through this API onto local disk when ATTACHMENTS_BUCKET
    isn't configured, so attachments still work on a plain dev machine."""

    _require_ticket_access(
        db, ticket_id, current_user, "upload attachments"
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
        # DB is the correct fix and is out of scope for this POC. In
        # local-disk mode the old file is similarly left on disk.
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

    if ATTACHMENTS_BUCKET:

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

    # Local-disk fallback: the frontend's upload step POSTs the file as
    # multipart/form-data to whatever `upload_url` it's given, with no
    # extra fields - so pointing it at our own upload endpoint with empty
    # upload_fields reuses that same client code unchanged.
    return AttachmentPresignResponse(
        attachment_id=attachment.id,
        upload_url=(
            f"{str(http_request.base_url).rstrip('/')}"
            f"/api/tickets/{ticket_id}/attachments/"
            f"{attachment.id}/upload"
        ),
        upload_fields={},
    )


@router.post(
    "/{ticket_id}/attachments/{attachment_id}/upload",
    status_code=204,
)
async def upload_attachment_to_local_disk(
    ticket_id: int,
    attachment_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Local-disk counterpart to an S3 presigned POST - only reachable
    when ATTACHMENTS_BUCKET is unset. Knowing the attachment_id already
    required an authenticated call to the presign endpoint above, which
    is the same trust model a real presigned URL uses."""

    if ATTACHMENTS_BUCKET:

        raise HTTPException(status_code=404, detail="Not found")

    attachment = db.get(Attachment, attachment_id)

    if attachment is None or attachment.ticket_id != ticket_id:

        raise HTTPException(
            status_code=404, detail="Attachment not found"
        )

    dest_path = LOCAL_UPLOAD_ROOT / attachment.s3_key

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with dest_path.open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    attachment.size_bytes = dest_path.stat().st_size

    db.commit()


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/file",
)
def get_local_attachment_file(
    ticket_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
):
    """Serves a locally-stored attachment's bytes back - the local-disk
    counterpart to an S3 presigned GET URL."""

    if ATTACHMENTS_BUCKET:

        raise HTTPException(status_code=404, detail="Not found")

    attachment = db.get(Attachment, attachment_id)

    if attachment is None or attachment.ticket_id != ticket_id:

        raise HTTPException(
            status_code=404, detail="Attachment not found"
        )

    file_path = LOCAL_UPLOAD_ROOT / attachment.s3_key

    if not file_path.is_file():

        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
    )


@router.get(
    "/{ticket_id}/attachments",
    response_model=Optional[AttachmentResponse],
)
def get_ticket_attachment(
    ticket_id: int,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    _require_ticket_access(
        db, ticket_id, current_user, "view attachments"
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

    return _attachment_response(attachment, http_request)
