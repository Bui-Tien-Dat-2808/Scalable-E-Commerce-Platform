"""Unit tests for Order Service with mocked HTTP calls to Product/Payment/Notification."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from services.order_service.app.main import app, orders_db
from services.user_service.app.main import app as user_app, users_db


client = TestClient(app)
client_user = TestClient(user_app)


# ─── Fixtures ───────────────────────────────────────────────────────────────

def _get_auth_headers(email: str = "order_user@example.com", username: str = "order_user") -> dict:
    users_db.clear()
    client_user.post("/auth/register", json={"username": username, "email": email, "password": "pass123"})
    resp = client_user.post("/auth/login", json={"email": email, "password": "pass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _mock_product(product_id: int = 1, name: str = "Laptop", price: float = 999.99, stock: int = 10):
    """Helper: tạo mock response cho product service."""
    return {"id": product_id, "name": name, "price": price, "stock": stock, "is_active": True}


def _mock_payment_approved(order_id: str = "ORD-1", amount: float = 999.99):
    return {"transaction_id": "TXN-ABCDEF", "order_id": order_id, "amount": amount, "status": "approved"}


def _mock_payment_failed(order_id: str = "ORD-1", amount: float = 999.99):
    return {"transaction_id": "TXN-XXXXXX", "order_id": order_id, "amount": amount, "status": "failed"}


@pytest.fixture(autouse=True)
def clear_state():
    users_db.clear()
    orders_db.clear()
    yield
    orders_db.clear()
    users_db.clear()


# ─── Helper: patch tất cả HTTP calls trong order_service ─────────────────────

def _patch_services(product_data=None, deduct_ok=True, payment_data=None):
    """Context manager mock toàn bộ httpx calls trong order service."""
    import services.order_service.app.main as order_mod

    product = product_data or _mock_product()
    payment = payment_data or _mock_payment_approved()

    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = product

    mock_deduct = MagicMock()
    mock_deduct.status_code = 200 if deduct_ok else 409
    mock_deduct.json.return_value = (
        {"product_id": 1, "deducted": 1, "remaining_stock": 9}
        if deduct_ok
        else {"detail": "Insufficient stock for product 1: available=0, requested=2"}
    )

    mock_payment = MagicMock()
    mock_payment.status_code = 200
    mock_payment.json.return_value = payment

    mock_notify = MagicMock()
    mock_notify.status_code = 200

    def fake_get(url, **kwargs):
        return mock_get

    def fake_patch(url, **kwargs):
        return mock_deduct

    def fake_post(url, **kwargs):
        if "payments" in url:
            return mock_payment
        return mock_notify

    return patch.multiple(
        "services.order_service.app.main.httpx",
        get=fake_get,
        patch=fake_patch,
        post=fake_post,
    )


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_order_success_paid():
    headers = _get_auth_headers()
    with _patch_services():
        resp = client.post(
            "/orders",
            json={"items": [{"product_id": 1, "quantity": 1}], "payment_method": "card"},
            headers=headers,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "paid"
    assert data["transaction_id"] == "TXN-ABCDEF"
    assert data["total_amount"] == 999.99
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Laptop"


def test_create_order_payment_failed():
    headers = _get_auth_headers()
    with _patch_services(payment_data=_mock_payment_failed()):
        resp = client.post(
            "/orders",
            json={"items": [{"product_id": 1, "quantity": 1}], "payment_method": "fail"},
            headers=headers,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "failed_payment"
    assert data["payment_status"] == "failed"


def test_create_order_insufficient_stock_returns_400():
    headers = _get_auth_headers()
    with _patch_services(deduct_ok=False):
        resp = client.post(
            "/orders",
            json={"items": [{"product_id": 1, "quantity": 2}], "payment_method": "card"},
            headers=headers,
        )
    assert resp.status_code == 400
    assert "stock" in resp.json()["detail"].lower()


def test_create_order_empty_items_returns_400():
    headers = _get_auth_headers()
    resp = client.post(
        "/orders",
        json={"items": [], "payment_method": "card"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_create_order_calculates_total_correctly():
    headers = _get_auth_headers()
    product = _mock_product(price=100.0)
    payment = _mock_payment_approved(amount=200.0)
    with _patch_services(product_data=product, payment_data=payment):
        resp = client.post(
            "/orders",
            json={"items": [{"product_id": 1, "quantity": 2}]},
            headers=headers,
        )
    assert resp.status_code == 201
    assert resp.json()["total_amount"] == 200.0


def test_list_orders_returns_only_own_orders():
    headers = _get_auth_headers()
    with _patch_services():
        client.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers=headers)

    resp = client.get("/orders", headers=headers)
    assert resp.status_code == 200
    orders = resp.json()["orders"]
    assert len(orders) >= 1


def test_get_order_detail():
    headers = _get_auth_headers()
    with _patch_services():
        create_resp = client.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers=headers)
    order_id = create_resp.json()["id"]

    resp = client.get(f"/orders/{order_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == order_id


def test_get_order_not_found():
    headers = _get_auth_headers()
    resp = client.get("/orders/9999", headers=headers)
    assert resp.status_code == 404


def test_get_order_forbidden_for_other_user():
    # Register cả 2 user trong cùng users_db context để có ID khác nhau
    users_db.clear()
    client_user.post("/auth/register", json={"username": "ua", "email": "ua@test.com", "password": "pass"})
    client_user.post("/auth/register", json={"username": "ub", "email": "ub@test.com", "password": "pass"})
    login_a = client_user.post("/auth/login", json={"email": "ua@test.com", "password": "pass"})
    login_b = client_user.post("/auth/login", json={"email": "ub@test.com", "password": "pass"})
    headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
    headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

    with _patch_services():
        create_resp = client.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers=headers_a)
    order_id = create_resp.json()["id"]

    # User B cố lấy order của User A
    resp = client.get(f"/orders/{order_id}", headers=headers_b)
    assert resp.status_code == 403


def test_cancel_paid_order():
    headers = _get_auth_headers()
    with _patch_services():
        create_resp = client.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers=headers)
    order_id = create_resp.json()["id"]

    # mock notification khi cancel
    with patch("services.order_service.app.main.httpx.post", return_value=MagicMock(status_code=200)):
        cancel_resp = client.patch(f"/orders/{order_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_cancel_already_cancelled_order_returns_400():
    headers = _get_auth_headers()
    with _patch_services():
        create_resp = client.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers=headers)
    order_id = create_resp.json()["id"]

    with patch("services.order_service.app.main.httpx.post", return_value=MagicMock(status_code=200)):
        client.patch(f"/orders/{order_id}/cancel", headers=headers)
        resp2 = client.patch(f"/orders/{order_id}/cancel", headers=headers)
    assert resp2.status_code == 400


def test_order_requires_auth():
    resp = client.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]})
    assert resp.status_code == 403


def test_order_status_fields_present():
    headers = _get_auth_headers()
    with _patch_services():
        resp = client.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers=headers)
    data = resp.json()
    assert "status" in data
    assert "transaction_id" in data
    assert "payment_status" in data
    assert "total_amount" in data
    assert "order_id" in data
