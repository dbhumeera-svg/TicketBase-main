from fastapi.testclient import TestClient

from src.main import app
from conftest import register_and_login, reset_db


client = TestClient(app)


def setup_function():
    reset_db()


def _headers():
    return register_and_login(client, "attach_user")


def _create_ticket(headers):

    response = client.post(
        "/api/tickets",
        json={
            "title": "Screen is broken",
            "description": (
                "The monitor shows no signal."
            ),
            "priority": "HIGH",
        },
        headers=headers,
    )

    return response.json()["id"]


def test_presign_requires_auth():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    response = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
    )

    assert response.status_code == 401


def test_presign_upload():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    response = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
        headers=headers,
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


def test_presign_forbidden_for_unrelated_user():

    owner_headers = _headers()
    ticket_id = _create_ticket(owner_headers)

    stranger_headers = register_and_login(
        client, "attach_stranger"
    )

    response = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
        headers=stranger_headers,
    )

    assert response.status_code == 403


def test_presign_rejects_bad_type():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    response = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "notes.txt",
            "content_type": "text/plain",
        },
        headers=headers,
    )

    assert response.status_code == 415


def test_presign_missing_ticket():

    headers = _headers()

    response = client.post(
        "/api/tickets/999/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
        headers=headers,
    )

    assert response.status_code == 404


def test_get_attachment_after_presign():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
        headers=headers,
    )

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments",
        headers=headers,
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

    headers = _headers()
    ticket_id = _create_ticket(headers)

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() is None


def test_get_attachment_missing_ticket():

    headers = _headers()

    response = client.get(
        "/api/tickets/999/attachments", headers=headers
    )

    assert response.status_code == 404


def test_re_presign_replaces_existing_attachment():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "first.png",
            "content_type": "image/png",
        },
        headers=headers,
    )

    client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "second.png",
            "content_type": "image/png",
        },
        headers=headers,
    )

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments",
        headers=headers,
    )

    assert response.json()["original_filename"] == "second.png"
