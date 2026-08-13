from fastapi.testclient import TestClient

from src.main import app
from conftest import auth_header, login, register_and_login, reset_db


client = TestClient(app)


def setup_function():
    reset_db()


def _admin_headers():
    return auth_header(login(client, "admin", "Admin@1234"))


def _create_ticket(headers, **overrides):
    payload = {
        "title": "Laptop issue",
        "description": "The laptop is not starting.",
        "category": "HARDWARE",
        "priority": "HIGH",
    }
    payload.update(overrides)

    return client.post("/api/tickets", json=payload, headers=headers)


def test_dashboard_requires_agent_or_admin():

    user_headers = register_and_login(client, "dana")

    response = client.get(
        "/api/tickets/dashboard", headers=user_headers
    )

    assert response.status_code == 403


def test_dashboard_empty():

    response = client.get(
        "/api/tickets/dashboard", headers=_admin_headers()
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total_tickets"] == 0
    assert data["by_status"]["OPEN"] == 0
    assert data["by_priority"]["MEDIUM"] == 0


def test_dashboard_counts():

    user_headers = register_and_login(client, "ellis")
    agent_headers = register_and_login(
        client, "farah", role="AGENT"
    )

    ticket_id = _create_ticket(
        user_headers,
        title="Laptop issue",
        description="The laptop is not starting.",
        category="HARDWARE",
        priority="HIGH",
    ).json()["id"]

    _create_ticket(
        user_headers,
        title="VPN issue",
        description="The VPN is not connecting.",
        category="NETWORK",
        priority="LOW",
    )

    client.patch(
        f"/api/tickets/{ticket_id}/status",
        json={"status": "IN_PROGRESS"},
        headers=agent_headers,
    )

    response = client.get(
        "/api/tickets/dashboard", headers=_admin_headers()
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total_tickets"] == 2
    assert data["by_status"]["IN_PROGRESS"] == 1
    assert data["by_status"]["OPEN"] == 1
    assert data["by_priority"]["HIGH"] == 1
    assert data["by_priority"]["LOW"] == 1
