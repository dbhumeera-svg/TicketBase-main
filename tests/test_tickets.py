from fastapi.testclient import TestClient

from src.database import (
    Base,
    SessionLocal,
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




def test_create_ticket():

    payload = {
    "title": "Laptop is not starting",
    "description": (
        "The laptop shows a black screen "
        "after pressing the power button."
    ),
    "category": "HARDWARE",
    "priority": "HIGH",
}

    response = client.post(
        "/api/tickets",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == 1
    assert data["title"] == (
        "Laptop is not starting"
    )
    assert data["priority"] == "HIGH"
    assert data["category"] == "HARDWARE"
    assert data["status"] == "OPEN"
    assert "created_at" in data
    assert "updated_at" in data


def test_get_all_tickets():

    payload = {
        "title": "VPN is not connecting",
        "description": (
            "The VPN connection fails "
            "during login."
        ),
        "priority": "MEDIUM",
    }

    client.post(
        "/api/tickets",
        json=payload,
    )

    response = client.get("/api/tickets")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == (
        "VPN is not connecting"
    )


def test_get_ticket_by_id():

    payload = {
        "title": "Email is not working",
        "description": (
            "Unable to send or receive "
            "emails."
        ),
        "priority": "HIGH",
    }

    client.post(
        "/api/tickets",
        json=payload,
    )

    response = client.get(
        "/api/tickets/1"
    )

    assert response.status_code == 200

    assert response.json()["id"] == 1


def test_ticket_not_found():

    response = client.get(
        "/api/tickets/999"
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Ticket not found"
    )


def test_update_ticket_status():

    payload = {
        "title": "System is slow",
        "description": (
            "The system takes several "
            "minutes to open applications."
        ),
        "priority": "LOW",
    }

    client.post(
        "/api/tickets",
        json=payload,
    )

    response = client.patch(
        "/api/tickets/1/status",
        json={
            "status": "IN_PROGRESS"
        },
    )

    assert response.status_code == 200

    assert (
        response.json()["status"]
        == "IN_PROGRESS"
    )


def test_delete_ticket():

    payload = {
        "title": "Printer issue",
        "description": (
            "The printer is not printing "
            "documents."
        ),
        "priority": "MEDIUM",
    }

    client.post(
        "/api/tickets",
        json=payload,
    )

    response = client.delete(
        "/api/tickets/1"
    )

    assert response.status_code == 200

    assert response.json() == {
        "message": (
            "Ticket deleted successfully"
        )
    }


def test_invalid_ticket_title():

    payload = {
        "title": "A",
        "description": (
            "The ticket title is too short."
        ),
        "priority": "HIGH",
    }

    response = client.post(
        "/api/tickets",
        json=payload,
    )

    assert response.status_code == 422
    
    
def test_add_comment():

    ticket_payload = {
        "title": "Laptop is not starting",
        "description": (
            "The laptop shows a black screen."
        ),
        "priority": "HIGH",
    }

    client.post(
        "/api/tickets",
        json=ticket_payload,
    )

    comment_payload = {
        "author": "Bhumeera",
        "message": (
            "The issue was assigned "
            "to the IT team."
        ),
    }

    response = client.post(
        "/api/tickets/1/comments",
        json=comment_payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["ticket_id"] == 1
    assert data["author"] == "Bhumeera"
    assert "created_at" in data


def test_get_ticket_comments():

    ticket_payload = {
        "title": "VPN issue",
        "description": (
            "The VPN connection is failing."
        ),
        "priority": "MEDIUM",
    }

    client.post(
        "/api/tickets",
        json=ticket_payload,
    )

    client.post(
        "/api/tickets/1/comments",
        json={
            "author": "Support Team",
            "message": (
                "We are investigating "
                "the issue."
            ),
        },
    )

    response = client.get(
        "/api/tickets/1/comments"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["author"] == (
        "Support Team"
    )


def test_add_comment_to_missing_ticket():

    response = client.post(
        "/api/tickets/999/comments",
        json={
            "author": "Bhumeera",
            "message": (
                "Checking the issue."
            ),
        },
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Ticket not found"
    )
    
    
def test_filter_tickets_by_priority():
    client.post(
        "/api/tickets",
        json={
            "title": "Laptop issue",
            "description": (
                "The laptop is not starting."
            ),
            "category": "HARDWARE",
            "priority": "HIGH",
        },
    )

    client.post(
        "/api/tickets",
        json={
            "title": "VPN issue",
            "description": (
                "The VPN is not connecting."
            ),
            "category": "NETWORK",
            "priority": "LOW",
        },
    )

    response = client.get(
        "/api/tickets?priority=HIGH"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["priority"] == "HIGH"


def test_filter_tickets_by_category():

    client.post(
        "/api/tickets",
        json={
            "title": "Printer issue",
            "description": (
                "The printer is not printing."
            ),
            "category": "HARDWARE",
            "priority": "MEDIUM",
        },
    )

    client.post(
        "/api/tickets",
        json={
            "title": "Email issue",
            "description": (
                "Unable to send emails."
            ),
            "category": "SOFTWARE",
            "priority": "HIGH",
        },
    )

    response = client.get(
        "/api/tickets?category=HARDWARE"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["category"] == (
        "HARDWARE"
    )


def test_filter_tickets_by_status():

    client.post(
        "/api/tickets",
        json={
            "title": "System issue",
            "description": (
                "The system is running slowly."
            ),
            "category": "SOFTWARE",
            "priority": "MEDIUM",
        },
    )

    client.patch(
        "/api/tickets/1/status",
        json={
            "status": "IN_PROGRESS"
        },
    )

    response = client.get(
        "/api/tickets?status=IN_PROGRESS"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["status"] == (
        "IN_PROGRESS"
    )