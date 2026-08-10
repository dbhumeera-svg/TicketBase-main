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


def test_dashboard_empty():

    response = client.get("/api/dashboard")

    assert response.status_code == 200

    data = response.json()

    assert data["total_tickets"] == 0
    assert data["by_status"]["OPEN"] == 0
    assert data["by_priority"]["MEDIUM"] == 0


def test_dashboard_counts():

    client.post(
        "/api/tickets",
        json={
            "title": "Laptop issue",
            "description": "The laptop is not starting.",
            "category": "HARDWARE",
            "priority": "HIGH",
        },
    )

    client.post(
        "/api/tickets",
        json={
            "title": "VPN issue",
            "description": "The VPN is not connecting.",
            "category": "NETWORK",
            "priority": "LOW",
        },
    )

    client.patch(
        "/api/tickets/1/status",
        json={"status": "IN_PROGRESS"},
    )

    response = client.get("/api/dashboard")

    assert response.status_code == 200

    data = response.json()

    assert data["total_tickets"] == 2
    assert data["by_status"]["IN_PROGRESS"] == 1
    assert data["by_status"]["OPEN"] == 1
    assert data["by_priority"]["HIGH"] == 1
    assert data["by_priority"]["LOW"] == 1
