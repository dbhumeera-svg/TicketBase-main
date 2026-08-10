"""S3-triggered thumbnail generator (M5).

Fired by an S3 ObjectCreated event on the `attachments/` prefix of the
TicketDesk attachments bucket. Downloads the object, resizes it, and
writes a PNG thumbnail to the `thumbnails/` prefix of the *same* bucket -
never back to `attachments/`, which would re-trigger this function.

The API never touches the file bytes for either the original upload
(browser -> presigned S3 URL) or the thumbnail (this function writes it
directly) - it only ever hands out presigned GET URLs for both.
"""

import io
import logging
import os

import boto3
from PIL import Image

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

THUMBNAIL_SIZE = (200, 200)

# Anything under this prefix skips resizing (PDFs aren't images - Pillow
# can't thumbnail them, so there's nothing useful to generate here yet).
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif"}


def _thumbnail_key(original_key: str) -> str:
    suffix = original_key.removeprefix("attachments/")
    return f"thumbnails/{suffix}.png"


def handler(event, context):
    results = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        if not key.startswith("attachments/"):
            logger.info("Skipping non-attachment key: %s", key)
            continue

        head = s3.head_object(Bucket=bucket, Key=key)
        content_type = head.get("ContentType", "")

        if content_type not in IMAGE_CONTENT_TYPES:
            logger.info(
                "Skipping non-image attachment (%s): %s",
                content_type,
                key,
            )
            continue

        obj = s3.get_object(Bucket=bucket, Key=key)
        image = Image.open(io.BytesIO(obj["Body"].read()))
        image = image.convert("RGB")
        image.thumbnail(THUMBNAIL_SIZE)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        thumb_key = _thumbnail_key(key)

        s3.put_object(
            Bucket=bucket,
            Key=thumb_key,
            Body=buffer,
            ContentType="image/png",
        )

        logger.info("Wrote thumbnail: %s -> %s", key, thumb_key)
        results.append(thumb_key)

    return {"thumbnails_written": results}
