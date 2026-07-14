from fastapi.testclient import TestClient

from services.user_service.app.main import app
from services.user_service.app.main import users_db


client = TestClient(app)


def setup_function():
    users_db.clear()


def test_root_route():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "user-service"


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "user-service"


def test_register_user():
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "supersecret",
    }
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json()["email"] == payload["email"]


def test_login_returns_jwt_access_token():
    client.post(
        "/auth/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "supersecret",
        },
    )

    response = client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "supersecret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "bob@example.com"
