"""Covers the local-disk fallback used when ATTACHMENTS_BUCKET isn't set
(see src/routers/attachments.py) - the path a plain dev machine with no
AWS account actually exercises."""

import io
import shutil

from fastapi.testclient import TestClient

import src.routers.attachments as attachments_module
from src.main import app
from conftest import register_and_login, reset_db


client = TestClient(app)

LOCAL_UPLOAD_DIR = attachments_module.LOCAL_UPLOAD_ROOT

# Other test modules (test_attachments.py) rely on ATTACHMENTS_BUCKET
# being set, so this module's tests must restore it afterward rather
# than leaving the shared module attribute mutated.
_ORIGINAL_BUCKET = attachments_module.ATTACHMENTS_BUCKET


def setup_function():
    reset_db()
    attachments_module.ATTACHMENTS_BUCKET = None

    if LOCAL_UPLOAD_DIR.exists():
        shutil.rmtree(LOCAL_UPLOAD_DIR)


def teardown_function():
    attachments_module.ATTACHMENTS_BUCKET = _ORIGINAL_BUCKET

    if LOCAL_UPLOAD_DIR.exists():
        shutil.rmtree(LOCAL_UPLOAD_DIR)


def _headers():
    return register_and_login(client, "local_attach_user")


def _create_ticket(headers):
    response = client.post(
        "/api/tickets",
        json={
            "title": "Screen is broken",
            "description": "The monitor shows no signal.",
            "priority": "HIGH",
        },
        headers=headers,
    )
    return response.json()["id"]


def test_presign_without_bucket_returns_local_upload_url():

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

    assert data["upload_fields"] == {}
    assert "/attachments/" in data["upload_url"]
    assert data["upload_url"].endswith(
        f"/attachments/{data['attachment_id']}/upload"
    )


def test_full_local_upload_and_download_roundtrip():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    presign = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
        headers=headers,
    ).json()

    attachment_id = presign["attachment_id"]

    fake_png_bytes = b"\x89PNG\r\n\x1a\nnot a real png but good enough"

    upload_path = (
        f"/api/tickets/{ticket_id}/attachments/"
        f"{attachment_id}/upload"
    )

    upload_response = client.post(
        upload_path,
        files={"file": ("screenshot.png", io.BytesIO(fake_png_bytes), "image/png")},
    )

    assert upload_response.status_code == 204

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments", headers=headers
    )

    assert response.status_code == 200

    data = response.json()

    assert data["original_filename"] == "screenshot.png"
    assert data["size_bytes"] == len(fake_png_bytes)
    assert f"/attachments/{attachment_id}/file" in data["download_url"]
    assert data["download_url"] == data["thumbnail_url"]

    file_response = client.get(data["download_url"])

    assert file_response.status_code == 200
    assert file_response.content == fake_png_bytes


def test_upload_rejects_mismatched_ticket_id():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    presign = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
        headers=headers,
    ).json()

    other_ticket_id = _create_ticket(headers)

    response = client.post(
        f"/api/tickets/{other_ticket_id}/attachments/"
        f"{presign['attachment_id']}/upload",
        files={"file": ("x.png", io.BytesIO(b"data"), "image/png")},
    )

    assert response.status_code == 404


def test_file_endpoint_404_before_upload():

    headers = _headers()
    ticket_id = _create_ticket(headers)

    presign = client.post(
        f"/api/tickets/{ticket_id}/attachments/presign",
        json={
            "filename": "screenshot.png",
            "content_type": "image/png",
        },
        headers=headers,
    ).json()

    response = client.get(
        f"/api/tickets/{ticket_id}/attachments/"
        f"{presign['attachment_id']}/file"
    )

    assert response.status_code == 404
