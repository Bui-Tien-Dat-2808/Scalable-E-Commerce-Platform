import pytest
from fastapi.testclient import TestClient

from services.user_service.app.main import app
from services.common.database import Base, engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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
