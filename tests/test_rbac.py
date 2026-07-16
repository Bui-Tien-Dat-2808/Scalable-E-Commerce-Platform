"""
RBAC Tests — kiểm tra phân quyền admin/user trên Product Service.
"""
import pytest
from fastapi.testclient import TestClient

from services.user_service.app.main import app as user_app, UserModel
from services.product_service.app.main import app as product_app, ProductModel
from services.common.database import Base, engine, SessionLocal
from services.common.security import hash_password

client_user = TestClient(user_app)
client_product = TestClient(product_app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Seed 1 product để test DELETE/PUT
    with SessionLocal() as db:
        db.add(ProductModel(id=1, name="Test Product", price=100.0, stock=5))
        db.commit()
    yield
    Base.metadata.drop_all(bind=engine)


def _user_token() -> str:
    """Đăng ký + login user thường, trả về access_token."""
    client_user.post("/auth/register", json={
        "username": "regularuser",
        "email": "user@test.com",
        "password": "UserPass123!",
    })
    resp = client_user.post("/auth/login", json={
        "email": "user@test.com",
        "password": "UserPass123!",
    })
    return resp.json()["access_token"]


def _admin_token() -> str:
    """Seed admin trực tiếp vào DB + login, trả về access_token."""
    with SessionLocal() as db:
        existing = db.query(UserModel).filter(UserModel.email == "admin@test.com").first()
        if not existing:
            db.add(UserModel(
                username="admin",
                email="admin@test.com",
                password=hash_password("AdminPass123!"),
                role="admin",
            ))
            db.commit()
    resp = client_user.post("/auth/login", json={
        "email": "admin@test.com",
        "password": "AdminPass123!",
    })
    return resp.json()["access_token"]


# ── POST /products ─────────────────────────────────────────────────────────────

def test_user_cannot_create_product():
    """User thường gọi POST /products → phải nhận 403 Forbidden."""
    token = _user_token()
    resp = client_product.post(
        "/products",
        json={"name": "New Product", "price": 50.0, "stock": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_unauthenticated_cannot_create_product():
    """Không có token gọi POST /products → phải nhận 403."""
    resp = client_product.post(
        "/products",
        json={"name": "New Product", "price": 50.0, "stock": 10},
    )
    assert resp.status_code in (401, 403)


def test_admin_can_create_product():
    """Admin gọi POST /products → phải nhận 201 Created."""
    token = _admin_token()
    resp = client_product.post(
        "/products",
        json={"name": "Admin Product", "price": 99.99, "stock": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Admin Product"


# ── PUT /products/{id} ────────────────────────────────────────────────────────

def test_user_cannot_update_product():
    """User thường gọi PUT /products/1 → phải nhận 403."""
    token = _user_token()
    resp = client_product.put(
        "/products/1",
        json={"name": "Updated", "price": 200.0, "stock": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_can_update_product():
    """Admin gọi PUT /products/1 → phải nhận 200."""
    token = _admin_token()
    resp = client_product.put(
        "/products/1",
        json={"name": "Updated by Admin", "price": 200.0, "stock": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated by Admin"


# ── DELETE /products/{id} ─────────────────────────────────────────────────────

def test_user_cannot_delete_product():
    """User thường gọi DELETE /products/1 → phải nhận 403."""
    token = _user_token()
    resp = client_product.delete(
        "/products/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_can_delete_product():
    """Admin gọi DELETE /products/1 → phải nhận 200 và is_active=False."""
    token = _admin_token()
    resp = client_product.delete(
        "/products/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["product"]["is_active"] is False


# ── GET /products — public (không cần auth) ────────────────────────────────────

def test_anyone_can_list_products():
    """GET /products không cần auth — trả về 200."""
    resp = client_product.get("/products")
    assert resp.status_code == 200
    assert "data" in resp.json()


def test_anyone_can_get_product_by_id():
    """GET /products/1 không cần auth — trả về 200."""
    resp = client_product.get("/products/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1
