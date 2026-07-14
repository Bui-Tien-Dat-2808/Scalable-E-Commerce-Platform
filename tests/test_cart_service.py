"""Unit tests for Cart Service."""
import pytest
from fastapi.testclient import TestClient

from services.cart_service.app.main import app
from services.user_service.app.main import app as user_app
from services.common.database import Base, engine

client = TestClient(app)
client_user = TestClient(user_app)


def _get_auth_headers(email: str = "cart_user@example.com", username: str = "cart_user") -> dict:
    client_user.post("/auth/register", json={"username": username, "email": email, "password": "pass123"})
    resp = client_user.post("/auth/login", json={"email": email, "password": "pass123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_get_empty_cart():
    headers = _get_auth_headers()
    resp = client.get("/cart", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []


def test_add_item_to_cart():
    headers = _get_auth_headers()
    resp = client.post("/cart/items", json={"product_id": 1, "quantity": 3}, headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["product_id"] == 1 and i["quantity"] == 3 for i in items)


def test_add_same_item_accumulates_quantity():
    headers = _get_auth_headers()
    client.post("/cart/items", json={"product_id": 1, "quantity": 2}, headers=headers)
    client.post("/cart/items", json={"product_id": 1, "quantity": 3}, headers=headers)
    resp = client.get("/cart", headers=headers)
    items = resp.json()["items"]
    item = next(i for i in items if i["product_id"] == 1)
    assert item["quantity"] == 5


def test_add_multiple_different_items():
    headers = _get_auth_headers()
    client.post("/cart/items", json={"product_id": 1, "quantity": 1}, headers=headers)
    client.post("/cart/items", json={"product_id": 2, "quantity": 2}, headers=headers)
    resp = client.get("/cart", headers=headers)
    items = resp.json()["items"]
    assert len(items) == 2


def test_update_item_quantity():
    headers = _get_auth_headers()
    client.post("/cart/items", json={"product_id": 1, "quantity": 2}, headers=headers)
    resp = client.put("/cart/items/1", json={"quantity": 5}, headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    item = next(i for i in items if i["product_id"] == 1)
    assert item["quantity"] == 5


def test_update_nonexistent_item_returns_404():
    headers = _get_auth_headers()
    resp = client.put("/cart/items/999", json={"quantity": 5}, headers=headers)
    assert resp.status_code == 404


def test_update_item_zero_quantity_returns_400():
    headers = _get_auth_headers()
    client.post("/cart/items", json={"product_id": 1, "quantity": 2}, headers=headers)
    resp = client.put("/cart/items/1", json={"quantity": 0}, headers=headers)
    assert resp.status_code == 400


def test_delete_item_from_cart():
    headers = _get_auth_headers()
    client.post("/cart/items", json={"product_id": 1, "quantity": 2}, headers=headers)
    resp = client.delete("/cart/items/1", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert not any(i["product_id"] == 1 for i in items)


def test_delete_nonexistent_item_returns_404():
    headers = _get_auth_headers()
    resp = client.delete("/cart/items/999", headers=headers)
    assert resp.status_code == 404


def test_cart_requires_auth():
    resp = client.get("/cart")
    assert resp.status_code == 403


def test_add_to_cart_requires_auth():
    resp = client.post("/cart/items", json={"product_id": 1, "quantity": 1})
    assert resp.status_code == 403


def test_carts_are_isolated_per_user():
    """Giỏ hàng của user A không ảnh hưởng đến user B."""
    # Đăng ký cả 2 user trong cùng một database context để có ID khác nhau
    client_user.post("/auth/register", json={"username": "user_a", "email": "user_a@example.com", "password": "pass"})
    client_user.post("/auth/register", json={"username": "user_b", "email": "user_b@example.com", "password": "pass"})

    login_a = client_user.post("/auth/login", json={"email": "user_a@example.com", "password": "pass"})
    login_b = client_user.post("/auth/login", json={"email": "user_b@example.com", "password": "pass"})

    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    client.post("/cart/items", json={"product_id": 1, "quantity": 5}, headers=headers_a)

    resp_b = client.get("/cart", headers=headers_b)
    assert resp_b.json()["items"] == []
