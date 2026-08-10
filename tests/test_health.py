from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "UP"
    }
    
    
def test_database_health():

    response = client.get(
        "/api/health/database"
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "UP",
        "database": "CONNECTED",
    }