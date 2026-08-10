from fastapi.testclient import TestClient

from src.database import (
    Base,
    engine,
)
from src.main import app


client = TestClient(app)


def setup_function():

    Base.metadata.drop_all(
        bind=engine
    )

    Base.metadata.create_all(
        bind=engine
    )


def _create_ticket():

    response = client.post(
        "/api/tickets",
        json={
            "title": "Screen is broken",
            "description": (
                "The monitor shows no signal."
            ),
            "priority": "HIGH",
        },
    )

    return response.json()["id"]


def test_presign_upload():

    ticket_id = _create_ticket()

    response = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["attachment_id"] > 0
    assert data["upload_url"]
    # A presigned POST returns the fields the browser must submit
    # alongside the file - key, policy, signature, and whatever we asked
    # the server to enforce (Content-Type here).
    assert "key" in data["upload_fields"]
    assert data["upload_fields"]["Content-Type"] == "image/png"


def test_presign_rejects_bad_type():

    ticket_id = _create_ticket()

    response = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "notes.txt",
            "content_type": "text/plain",
        },
    )

    assert response.status_code == 415


def test_presign_missing_ticket():

    response = client.post(
        "/api/tickets/999/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
    )

    assert response.status_code == 404


def test_get_attachment_after_presign():

    ticket_id = _create_ticket()

    client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
    )

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["ticket_id"] == ticket_id
    assert data["original_filename"] == "screenshot.png"
    assert data["content_type"] == "image/png"
    # Not known until the browser finishes the direct-to-S3 upload, which
    # the API is never told about.
    assert data["size_bytes"] is None
    assert data["download_url"].startswith("https://")
    assert data["thumbnail_url"].startswith("https://")


def test_get_attachment_when_none_uploaded():

    ticket_id = _create_ticket()

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments"
    )

    assert response.status_code == 200
    assert response.json() is None


def test_get_attachment_missing_ticket():

    response = client.get(
        "/api/tickets/999/attachments"
    )

    assert response.status_code == 404


def test_re_presign_replaces_existing_attachment():

    ticket_id = _create_ticket()

    client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "first.png",
            "content_type": "image/png",
        },
    )

    client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "second.png",
            "content_type": "image/png",
        },
    )

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments"
    )

    assert response.json()["original_filename"] == "second.png"
