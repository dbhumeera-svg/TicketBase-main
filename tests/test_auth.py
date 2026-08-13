from fastapi.testclient import TestClient

import src.security as security
from src.main import app
from conftest import auth_header, login, reset_db


client = TestClient(app)


def setup_function():
    reset_db()


def test_register_creates_plain_user_by_default():

    response = client.post(
        "/api/auth/register",
        json={
            "username": "newbie",
            "email": "newbie@example.com",
            "password": "Password@123",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["role"] == "USER"
    assert data["username"] == "newbie"


def test_register_agent_role_allowed():

    response = client.post(
        "/api/auth/register",
        json={
            "username": "helper",
            "email": "helper@example.com",
            "password": "Password@123",
            "role": "AGENT",
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "AGENT"


def test_register_admin_role_rejected():

    response = client.post(
        "/api/auth/register",
        json={
            "username": "sneaky",
            "email": "sneaky@example.com",
            "password": "Password@123",
            "role": "ADMIN",
        },
    )

    assert response.status_code == 400


def test_register_duplicate_username_rejected():

    payload = {
        "username": "dupe",
        "email": "dupe1@example.com",
        "password": "Password@123",
    }

    client.post("/api/auth/register", json=payload)

    payload["email"] = "dupe2@example.com"

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 409


def test_register_duplicate_email_rejected():

    client.post(
        "/api/auth/register",
        json={
            "username": "one",
            "email": "same@example.com",
            "password": "Password@123",
        },
    )

    response = client.post(
        "/api/auth/register",
        json={
            "username": "two",
            "email": "same@example.com",
            "password": "Password@123",
        },
    )

    assert response.status_code == 409


def test_register_rejects_weak_password():

    response = client.post(
        "/api/auth/register",
        json={
            "username": "weakpw",
            "email": "weakpw@example.com",
            "password": "alllowercase",
        },
    )

    assert response.status_code == 422


def test_register_rejects_bad_username_characters():

    response = client.post(
        "/api/auth/register",
        json={
            "username": "bad user!",
            "email": "baduser@example.com",
            "password": "Password@123",
        },
    )

    assert response.status_code == 422


def test_login_success():

    client.post(
        "/api/auth/register",
        json={
            "username": "loginme",
            "email": "loginme@example.com",
            "password": "Password@123",
        },
    )

    response = client.post(
        "/api/auth/login",
        json={
            "username": "loginme",
            "password": "Password@123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["username"] == "loginme"
    assert data["token"]
    assert data["role"] == "USER"


def test_login_with_email():

    client.post(
        "/api/auth/register",
        json={
            "username": "emaillogin",
            "email": "emaillogin@example.com",
            "password": "Password@123",
        },
    )

    response = client.post(
        "/api/auth/login",
        json={
            "username": "emaillogin@example.com",
            "password": "Password@123",
        },
    )

    assert response.status_code == 200


def test_login_wrong_password():

    client.post(
        "/api/auth/register",
        json={
            "username": "badpw",
            "email": "badpw@example.com",
            "password": "Password@123",
        },
    )

    response = client.post(
        "/api/auth/login",
        json={
            "username": "badpw",
            "password": "WrongPass@1",
        },
    )

    assert response.status_code == 401


def test_login_unknown_user():

    response = client.post(
        "/api/auth/login",
        json={
            "username": "ghost",
            "password": "Password@123",
        },
    )

    assert response.status_code == 401


def test_seeded_admin_can_log_in():

    response = client.post(
        "/api/auth/login",
        json={
            "username": "admin",
            "password": "Admin@1234",
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"


def test_me_requires_token():

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user():

    client.post(
        "/api/auth/register",
        json={
            "username": "whoami",
            "email": "whoami@example.com",
            "password": "Password@123",
        },
    )

    token = login(client, "whoami")

    response = client.get(
        "/api/auth/me", headers=auth_header(token)
    )

    assert response.status_code == 200
    assert response.json()["username"] == "whoami"


def test_agents_list_requires_agent_or_admin():

    client.post(
        "/api/auth/register",
        json={
            "username": "plain",
            "email": "plain@example.com",
            "password": "Password@123",
        },
    )

    token = login(client, "plain")

    response = client.get(
        "/api/auth/agents", headers=auth_header(token)
    )

    assert response.status_code == 403


def test_agents_list_returns_only_agents():

    admin_token = login(client, "admin", "Admin@1234")

    response = client.get(
        "/api/auth/agents", headers=auth_header(admin_token)
    )

    assert response.status_code == 200

    usernames = [u["username"] for u in response.json()]

    assert "agent" in usernames
    assert "admin" not in usernames


def test_token_rejected_after_jwt_secret_rotates():
    """Simulates a dev server restart: JWT_SECRET is only ever the same
    across two runs if it's explicitly configured (src/security.py); a
    restart with no explicit secret mints a new random one, and any
    token issued before that must stop working."""

    token = login(client, "admin", "Admin@1234")

    response = client.get("/api/auth/me", headers=auth_header(token))
    assert response.status_code == 200

    original_secret = security.JWT_SECRET

    try:
        security.JWT_SECRET = "a-completely-different-secret"

        response = client.get("/api/auth/me", headers=auth_header(token))
        assert response.status_code == 401
    finally:
        security.JWT_SECRET = original_secret
