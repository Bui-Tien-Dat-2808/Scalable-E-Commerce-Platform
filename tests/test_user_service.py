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


def _register_and_login(email="bob@example.com", password="supersecret", username="bob"):
    client.post("/auth/register", json={"username": username, "email": email, "password": password})
    resp = client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()


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
    assert response.json()["role"] == "user"


def test_register_duplicate_email_returns_409():
    payload = {"username": "alice", "email": "alice@example.com", "password": "supersecret"}
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 409


def test_login_returns_jwt_access_token():
    client.post(
        "/auth/register",
        json={"username": "bob", "email": "bob@example.com", "password": "supersecret"},
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


def test_login_returns_refresh_token():
    """Login phải trả về cả access_token và refresh_token."""
    data = _register_and_login()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_refresh_token_returns_new_access_token():
    """POST /auth/refresh với refresh_token hợp lệ → trả access_token + refresh_token mới."""
    data = _register_and_login()
    old_access = data["access_token"]
    old_refresh = data["refresh_token"]

    resp = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    # Token mới phải khác token cũ
    assert body["access_token"] != old_access
    assert body["refresh_token"] != old_refresh


def test_refresh_token_rotation_revokes_old_token():
    """Sau khi rotate, refresh_token cũ KHÔNG thể dùng lại."""
    data = _register_and_login()
    old_refresh = data["refresh_token"]

    # Dùng lần 1 — thành công
    resp1 = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert resp1.status_code == 200

    # Dùng lại token cũ lần 2 — phải thất bại
    resp2 = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


def test_refresh_token_invalid_returns_401():
    resp = client.post("/auth/refresh", json={"refresh_token": "invalid.token.here"})
    assert resp.status_code == 401


def test_logout_revokes_refresh_token():
    """Sau khi logout, refresh_token không dùng được nữa."""
    data = _register_and_login()
    refresh = data["refresh_token"]

    logout_resp = client.post("/auth/logout", json={"refresh_token": refresh})
    assert logout_resp.status_code == 200

    # Thử refresh sau logout → phải fail
    refresh_resp = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refresh_resp.status_code == 401


def test_login_wrong_password_returns_401():
    client.post("/auth/register", json={"username": "charlie", "email": "charlie@example.com", "password": "correct"})
    resp = client.post("/auth/login", json={"email": "charlie@example.com", "password": "wrong_pass"})
    assert resp.status_code == 401


# ── Strict Validation Tests ───────────────────────────────────────────────────

def test_register_username_too_short():
    payload = {"username": "a", "email": "short@example.com", "password": "password123"}
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422  # Validation Error


def test_register_password_too_short():
    payload = {"username": "validname", "email": "shortpass@example.com", "password": "123"}
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422  # Validation Error


# ── User CRUD Tests ───────────────────────────────────────────────────────────

def _get_admin_token() -> str:
    from services.common.database import SessionLocal
    from services.user_service.app.main import UserModel
    from services.common.security import hash_password
    with SessionLocal() as db:
        admin = db.query(UserModel).filter(UserModel.email == "admin@test.com").first()
        if not admin:
            db.add(UserModel(
                username="admin",
                email="admin@test.com",
                password=hash_password("AdminPass123!"),
                role="admin"
            ))
            db.commit()
    resp = client.post("/auth/login", json={"email": "admin@test.com", "password": "AdminPass123!"})
    return resp.json()["access_token"]


def test_list_users_admin_success():
    token = _get_admin_token()
    # Register another user
    client.post("/auth/register", json={"username": "bob", "email": "bob@example.com", "password": "password123"})
    
    resp = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) >= 2  # bob + admin


def test_list_users_regular_user_forbidden():
    user_data = _register_and_login("user@example.com", "password123", "normaluser")
    token = user_data["access_token"]
    
    resp = client.get("/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403  # Forbidden


def test_get_user_own_profile_success():
    user_data = _register_and_login("user@example.com", "password123", "normaluser")
    token = user_data["access_token"]
    user_id = user_data["user"]["id"]
    
    resp = client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "user@example.com"


def test_get_user_other_profile_forbidden():
    user1_data = _register_and_login("user1@example.com", "password123", "user1")
    user2_data = _register_and_login("user2@example.com", "password123", "user2")
    
    token1 = user1_data["access_token"]
    user2_id = user2_data["user"]["id"]
    
    # User 1 tries to access User 2's data
    resp = client.get(f"/users/{user2_id}", headers={"Authorization": f"Bearer {token1}"})
    assert resp.status_code == 403


def test_update_user_own_profile_success():
    user_data = _register_and_login("user@example.com", "password123", "normaluser")
    token = user_data["access_token"]
    user_id = user_data["user"]["id"]
    
    resp = client.put(
        f"/users/{user_id}",
        json={"username": "updated_bob", "email": "new_bob@example.com"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "updated_bob"
    assert resp.json()["email"] == "new_bob@example.com"


def test_delete_user_admin_success():
    token = _get_admin_token()
    
    # Register bob to delete him
    bob_resp = client.post("/auth/register", json={"username": "bob", "email": "bob@example.com", "password": "password123"})
    bob_id = bob_resp.json()["id"]
    
    resp = client.delete(f"/users/{bob_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == bob_id
    
    # Verify bob is deleted
    verify_resp = client.get(f"/users/{bob_id}", headers={"Authorization": f"Bearer {token}"})
    assert verify_resp.status_code == 404
