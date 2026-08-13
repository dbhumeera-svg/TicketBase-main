from fastapi.testclient import TestClient

from src.main import app
from conftest import auth_header, login, register_and_login, reset_db


client = TestClient(app)


def setup_function():
    reset_db()


def _create_ticket(headers, **overrides):
    payload = {
        "title": "Laptop issue",
        "description": "The laptop is not starting.",
        "priority": "HIGH",
    }
    payload.update(overrides)

    return client.post("/api/tickets", json=payload, headers=headers)


def test_notifications_require_auth():

    response = client.get("/api/notifications")

    assert response.status_code == 401


def test_ticket_creation_notifies_creator():

    headers = register_and_login(client, "nora")

    _create_ticket(headers)

    response = client.get("/api/notifications", headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["type"] == "TICKET_CREATED"
    assert data[0]["is_read"] is False

    unread = client.get(
        "/api/notifications/unread-count", headers=headers
    )

    assert unread.json()["unread_count"] == 1


def test_status_change_notifies_creator_not_actor():

    user_headers = register_and_login(client, "oscar")
    agent_headers = register_and_login(
        client, "penny", role="AGENT"
    )
    admin_headers = auth_header(
        login(client, "admin", "Admin@1234")
    )

    ticket_id = _create_ticket(user_headers).json()["id"]

    agent_id = client.get(
        "/api/auth/me", headers=agent_headers
    ).json()["id"]

    client.patch(
        f"/api/tickets/{ticket_id}/assign",
        params={"agent_id": agent_id},
        headers=admin_headers,
    )

    client.patch(
        f"/api/tickets/{ticket_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=agent_headers,
    )

    # The agent made the change - they shouldn't be told about their
    # own action.
    agent_notifications = client.get(
        "/api/notifications", headers=agent_headers
    ).json()

    assert all(
        n["type"] != "STATUS_CHANGED"
        for n in agent_notifications
    )

    # The creator (a different person) should be notified.
    user_notifications = client.get(
        "/api/notifications", headers=user_headers
    ).json()

    assert any(
        n["type"] == "STATUS_CHANGED"
        for n in user_notifications
    )


def test_comment_notifies_the_other_party():

    user_headers = register_and_login(client, "quincy")
    agent_headers = register_and_login(
        client, "rachel", role="AGENT"
    )
    admin_headers = auth_header(
        login(client, "admin", "Admin@1234")
    )

    ticket_id = _create_ticket(user_headers).json()["id"]

    agent_id = client.get(
        "/api/auth/me", headers=agent_headers
    ).json()["id"]

    client.patch(
        f"/api/tickets/{ticket_id}/assign",
        params={"agent_id": agent_id},
        headers=admin_headers,
    )

    client.post(
        f"/api/tickets/{ticket_id}/comments",
        json={"message": "Looking into it."},
        headers=agent_headers,
    )

    user_notifications = client.get(
        "/api/notifications", headers=user_headers
    ).json()

    assert any(
        n["type"] == "COMMENT_ADDED"
        for n in user_notifications
    )

    agent_notifications = client.get(
        "/api/notifications", headers=agent_headers
    ).json()

    assert all(
        n["type"] != "COMMENT_ADDED"
        for n in agent_notifications
    )


def test_mark_notification_read():

    headers = register_and_login(client, "steve")

    _create_ticket(headers)

    notifications = client.get(
        "/api/notifications", headers=headers
    ).json()

    notification_id = notifications[0]["id"]

    response = client.patch(
        f"/api/notifications/{notification_id}/read",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["is_read"] is True

    unread = client.get(
        "/api/notifications/unread-count", headers=headers
    )

    assert unread.json()["unread_count"] == 0


def test_mark_all_notifications_read():

    headers = register_and_login(client, "tara")

    _create_ticket(headers)
    _create_ticket(
        headers,
        title="Second issue",
        description="Another problem entirely.",
    )

    response = client.patch(
        "/api/notifications/read-all", headers=headers
    )

    assert response.status_code == 200

    unread = client.get(
        "/api/notifications/unread-count", headers=headers
    )

    assert unread.json()["unread_count"] == 0


def test_cannot_read_someone_elses_notification():

    owner_headers = register_and_login(client, "uriel")

    _create_ticket(owner_headers)

    notification_id = client.get(
        "/api/notifications", headers=owner_headers
    ).json()[0]["id"]

    stranger_headers = register_and_login(client, "vera")

    response = client.patch(
        f"/api/notifications/{notification_id}/read",
        headers=stranger_headers,
    )

    assert response.status_code == 404
