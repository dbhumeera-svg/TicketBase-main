from fastapi.testclient import TestClient

from src.main import app
from conftest import (
    auth_header,
    login,
    register_and_login,
    reset_db,
)


client = TestClient(app)


def setup_function():
    reset_db()


def _user_headers(username="alice"):
    return register_and_login(client, username)


def _agent_headers(username="bob"):
    return register_and_login(client, username, role="AGENT")


def _admin_headers():
    return auth_header(login(client, "admin", "Admin@1234"))


def _user_id(headers):
    return client.get("/api/auth/me", headers=headers).json()["id"]


def _create_ticket(headers, **overrides):
    payload = {
        "title": "Laptop is not starting",
        "description": (
            "The laptop shows a black screen "
            "after pressing the power button."
        ),
        "category": "HARDWARE",
        "priority": "HIGH",
    }
    payload.update(overrides)

    return client.post("/api/tickets", json=payload, headers=headers)


def test_create_ticket_requires_auth():

    response = client.post(
        "/api/tickets",
        json={"title": "x", "description": "something is broken"},
    )

    assert response.status_code == 401


def test_create_ticket():

    headers = _user_headers()

    response = _create_ticket(headers)

    assert response.status_code == 201

    data = response.json()

    assert data["title"] == "Laptop is not starting"
    assert data["priority"] == "HIGH"
    assert data["category"] == "HARDWARE"
    assert data["status"] == "OPEN"
    assert data["created_by_username"] == "alice"
    assert data["assigned_to"] is None
    assert data["user_sequence"] == 1
    assert data["ticket_number"].startswith("TKT-")
    assert "created_at" in data
    assert "updated_at" in data


def test_get_all_tickets_scoped_to_creator():

    headers = _user_headers()

    _create_ticket(
        headers,
        title="VPN is not connecting",
        description="The VPN connection fails during login.",
        priority="MEDIUM",
    )

    response = client.get("/api/tickets", headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert data["items"][0]["title"] == "VPN is not connecting"


def test_agent_only_sees_assigned_tickets():

    user_headers = _user_headers("carol")
    agent_headers = _agent_headers("dave")
    admin_headers = _admin_headers()

    ticket_id = _create_ticket(user_headers).json()["id"]

    response = client.get("/api/tickets", headers=agent_headers)
    assert response.json()["total"] == 0

    agent_id = _user_id(agent_headers)

    client.patch(
        f"/api/tickets/{ticket_id}/assign",
        params={"agent_id": agent_id},
        headers=admin_headers,
    )

    response = client.get("/api/tickets", headers=agent_headers)
    assert response.json()["total"] == 1


def test_admin_sees_all_tickets_and_assigned_status_filter():

    user_headers = _user_headers("erin")

    _create_ticket(user_headers)

    admin_headers = _admin_headers()

    response = client.get("/api/tickets", headers=admin_headers)
    assert response.json()["total"] == 1

    response = client.get(
        "/api/tickets?assigned_status=unassigned",
        headers=admin_headers,
    )
    assert response.json()["total"] == 1

    response = client.get(
        "/api/tickets?assigned_status=assigned",
        headers=admin_headers,
    )
    assert response.json()["total"] == 0


def test_get_ticket_by_id():

    headers = _user_headers()

    ticket_id = _create_ticket(headers).json()["id"]

    response = client.get(f"/api/tickets/{ticket_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == ticket_id


def test_get_ticket_forbidden_for_unrelated_user():

    owner_headers = _user_headers("frank")
    stranger_headers = _user_headers("grace")

    ticket_id = _create_ticket(owner_headers).json()["id"]

    response = client.get(
        f"/api/tickets/{ticket_id}", headers=stranger_headers
    )

    assert response.status_code == 403


def test_ticket_not_found():

    headers = _user_headers()

    response = client.get("/api/tickets/999", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_update_ticket_status_by_agent():

    user_headers = _user_headers("hank")
    agent_headers = _agent_headers("iris")

    ticket_id = _create_ticket(user_headers).json()["id"]

    response = client.patch(
        f"/api/tickets/{ticket_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=agent_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"


def test_plain_user_cannot_update_status():

    headers = _user_headers("jill")

    ticket_id = _create_ticket(headers).json()["id"]

    response = client.patch(
        f"/api/tickets/{ticket_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=headers,
    )

    assert response.status_code == 403


def test_invalid_status_transition_rejected():

    user_headers = _user_headers("kate")
    agent_headers = _agent_headers("leo")

    ticket_id = _create_ticket(user_headers).json()["id"]

    # OPEN -> RESOLVED skips IN_PROGRESS, which the lifecycle forbids.
    response = client.patch(
        f"/api/tickets/{ticket_id}/status",
        json={"status": "RESOLVED"},
        headers=agent_headers,
    )

    assert response.status_code == 400


def test_full_status_lifecycle():

    user_headers = _user_headers("mia")
    agent_headers = _agent_headers("noah")

    ticket_id = _create_ticket(user_headers).json()["id"]

    for target in ("IN_PROGRESS", "RESOLVED", "CLOSED", "IN_PROGRESS"):

        response = client.patch(
            f"/api/tickets/{ticket_id}/status",
            json={"status": target},
            headers=agent_headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == target


def test_assign_ticket_admin_only():

    user_headers = _user_headers("owen")
    agent_headers = _agent_headers("paula")
    admin_headers = _admin_headers()

    ticket_id = _create_ticket(user_headers).json()["id"]
    agent_id = _user_id(agent_headers)

    forbidden = client.patch(
        f"/api/tickets/{ticket_id}/assign",
        params={"agent_id": agent_id},
        headers=agent_headers,
    )
    assert forbidden.status_code == 403

    response = client.patch(
        f"/api/tickets/{ticket_id}/assign",
        params={"agent_id": agent_id},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["assigned_to_username"] == "paula"


def test_delete_ticket_admin_only():

    user_headers = _user_headers("quinn")
    admin_headers = _admin_headers()

    ticket_id = _create_ticket(user_headers).json()["id"]

    forbidden = client.delete(
        f"/api/tickets/{ticket_id}", headers=user_headers
    )
    assert forbidden.status_code == 403

    response = client.delete(
        f"/api/tickets/{ticket_id}", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Ticket deleted successfully"
    }


def test_invalid_ticket_title():

    headers = _user_headers()

    response = _create_ticket(headers, title="A")

    assert response.status_code == 422


def test_add_comment():

    headers = _user_headers("rex")

    ticket_id = _create_ticket(headers).json()["id"]

    response = client.post(
        f"/api/tickets/{ticket_id}/comments",
        json={
            "message": "The issue was assigned to the IT team.",
        },
        headers=headers,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["ticket_id"] == ticket_id
    assert data["author_username"] == "rex"
    assert "created_at" in data


def test_comment_forbidden_for_unrelated_user():

    owner_headers = _user_headers("sam")
    stranger_headers = _user_headers("tina")

    ticket_id = _create_ticket(owner_headers).json()["id"]

    response = client.post(
        f"/api/tickets/{ticket_id}/comments",
        json={"message": "hi"},
        headers=stranger_headers,
    )

    assert response.status_code == 403


def test_get_ticket_comments():

    headers = _user_headers("uma")

    ticket_id = _create_ticket(headers).json()["id"]

    client.post(
        f"/api/tickets/{ticket_id}/comments",
        json={"message": "We are investigating the issue."},
        headers=headers,
    )

    response = client.get(
        f"/api/tickets/{ticket_id}/comments", headers=headers
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["message"] == "We are investigating the issue."


def test_add_comment_to_missing_ticket():

    headers = _user_headers()

    response = client.post(
        "/api/tickets/999/comments",
        json={"message": "Checking the issue."},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_filter_tickets_by_priority():

    headers = _user_headers("vic")

    _create_ticket(
        headers,
        title="Laptop issue",
        description="The laptop is not starting.",
        category="HARDWARE",
        priority="HIGH",
    )

    _create_ticket(
        headers,
        title="VPN issue",
        description="The VPN is not connecting.",
        category="NETWORK",
        priority="LOW",
    )

    response = client.get(
        "/api/tickets?priority=HIGH", headers=headers
    )

    data = response.json()

    assert data["total"] == 1
    assert data["items"][0]["priority"] == "HIGH"


def test_filter_tickets_by_category():

    headers = _user_headers("wade")

    _create_ticket(
        headers,
        title="Printer issue",
        description="The printer is not printing.",
        category="HARDWARE",
        priority="MEDIUM",
    )

    _create_ticket(
        headers,
        title="Email issue",
        description="Unable to send emails.",
        category="SOFTWARE",
        priority="HIGH",
    )

    response = client.get(
        "/api/tickets?category=HARDWARE", headers=headers
    )

    data = response.json()

    assert data["total"] == 1
    assert data["items"][0]["category"] == "HARDWARE"


def test_filter_tickets_by_status():

    user_headers = _user_headers("xena")
    agent_headers = _agent_headers("yuri")

    ticket_id = _create_ticket(
        user_headers,
        title="System issue",
        description="The system is running slowly.",
        category="SOFTWARE",
        priority="MEDIUM",
    ).json()["id"]

    client.patch(
        f"/api/tickets/{ticket_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=agent_headers,
    )

    response = client.get(
        "/api/tickets?status=IN_PROGRESS", headers=user_headers
    )

    data = response.json()

    assert data["total"] == 1
    assert data["items"][0]["status"] == "IN_PROGRESS"


def test_pagination():

    headers = _user_headers("zack")

    for i in range(3):
        _create_ticket(
            headers,
            title=f"Ticket {i}",
            description="Some longer description text here.",
        )

    response = client.get(
        "/api/tickets?page=1&size=2", headers=headers
    )
    data = response.json()

    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["total_pages"] == 2

    response = client.get(
        "/api/tickets?page=2&size=2", headers=headers
    )
    data = response.json()

    assert len(data["items"]) == 1
