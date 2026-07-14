"""MVP flow tests — kiểm tra từng service chạy đúng chức năng cơ bản."""
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from services.user_service.app.main import app as user_app
from services.user_service.app.main import users_db
from services.product_service.app.main import app as product_app
from services.product_service.app.main import products_db
from services.cart_service.app.main import app as cart_app
from services.cart_service.app.main import carts_db
from services.order_service.app.main import app as order_app
from services.order_service.app.main import orders_db
from services.payment_service.app.main import app as payment_app
from services.payment_service.app.main import payments_db, payments_by_order
from services.notification_service.app.main import app as notification_app
from services.notification_service.app.main import notifications_db


client_user = TestClient(user_app)
client_product = TestClient(product_app)
client_cart = TestClient(cart_app)
client_order = TestClient(order_app)
client_payment = TestClient(payment_app)
client_notification = TestClient(notification_app)


def setup_function():
    users_db.clear()
    products_db[:] = [
        {"id": 1, "name": "Laptop", "price": 999.99, "stock": 10, "is_active": True},
        {"id": 2, "name": "Smartphone", "price": 499.99, "stock": 20, "is_active": True},
    ]
    carts_db.clear()
    orders_db.clear()
    payments_db.clear()
    payments_by_order.clear()
    notifications_db.clear()


def _auth_headers() -> dict:
    email = "alice@example.com"
    client_user.post(
        "/auth/register",
        json={"username": "alice", "email": email, "password": "supersecret"},
    )
    login_response = client_user.post(
        "/auth/login",
        json={"email": email, "password": "supersecret"},
    )
    return {"Authorization": f"Bearer {login_response.json()['access_token']}"}


def test_register_and_login_flow():
    register_response = client_user.post(
        "/auth/register",
        json={"username": "carol", "email": "carol@example.com", "password": "supersecret"},
    )
    assert register_response.status_code == 201

    login_response = client_user.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": "supersecret"},
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()


def test_product_catalog_flow():
    create_response = client_product.post(
        "/products",
        json={"name": "Laptop", "price": 999.99, "stock": 10},
    )
    assert create_response.status_code == 201

    list_response = client_product.get("/products")
    assert list_response.status_code == 200
    assert any(item["name"] == "Laptop" for item in list_response.json()["products"])

    update_response = client_product.put(
        "/products/1",
        json={"name": "Laptop Pro", "price": 1099.99, "stock": 8},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Laptop Pro"

    delete_response = client_product.delete("/products/2")
    assert delete_response.status_code == 200
    assert delete_response.json()["product"]["is_active"] is False


def test_product_get_by_id():
    resp = client_product.get("/products/1")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_product_deduct_stock():
    resp = client_product.patch("/products/1/deduct-stock", json={"quantity": 3})
    assert resp.status_code == 200
    assert resp.json()["remaining_stock"] == 7  # 10 - 3


def test_product_deduct_stock_insufficient():
    resp = client_product.patch("/products/1/deduct-stock", json={"quantity": 999})
    assert resp.status_code == 409


def test_cart_flow():
    headers = _auth_headers()

    cart_response = client_cart.post(
        "/cart/items",
        json={"product_id": 1, "quantity": 2},
        headers=headers,
    )
    assert cart_response.status_code == 200

    cart_update = client_cart.put(
        "/cart/items/1",
        json={"quantity": 3},
        headers=headers,
    )
    assert cart_update.status_code == 200

    cart_view = client_cart.get("/cart", headers=headers)
    assert cart_view.status_code == 200
    assert cart_view.json()["user_id"] == "1"


def test_order_flow_with_mocked_services():
    """
    Order flow với mock HTTP calls tới product/payment/notification services.
    Order status phải là 'paid' sau khi payment approved.
    """
    headers = _auth_headers()

    mock_product = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"id": 1, "name": "Laptop", "price": 999.99, "stock": 10, "is_active": True}),
    )
    mock_deduct = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"product_id": 1, "deducted": 2, "remaining_stock": 8}),
    )
    mock_payment = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"transaction_id": "TXN-MVP01", "order_id": "ORD-1", "amount": 1999.98, "status": "approved"}),
    )
    mock_notify = MagicMock(status_code=200, json=MagicMock(return_value={"notification_id": "NTF-MVP01", "status": "queued"}))

    with patch.multiple(
        "services.order_service.app.main.httpx",
        get=lambda url, **kw: mock_product,
        patch=lambda url, **kw: mock_deduct,
        post=lambda url, **kw: mock_payment if "payments" in url else mock_notify,
    ):
        order_response = client_order.post(
            "/orders",
            json={"items": [{"product_id": 1, "quantity": 2}], "payment_method": "card"},
            headers=headers,
        )

    assert order_response.status_code == 201
    order_data = order_response.json()
    # Status phải là "paid" thay vì "created" như trước
    assert order_data["status"] == "paid"
    assert order_data["transaction_id"] == "TXN-MVP01"

    order_list = client_order.get("/orders", headers=headers)
    assert order_list.status_code == 200
    assert len(order_list.json()["orders"]) >= 1

    order_detail = client_order.get(f"/orders/{order_data['id']}", headers=headers)
    assert order_detail.status_code == 200

    with patch("services.order_service.app.main.httpx.post", return_value=mock_notify):
        cancel_response = client_order.patch(f"/orders/{order_data['id']}/cancel", headers=headers)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_payment_and_notification_flow():
    payment_response = client_payment.post(
        "/payments/checkout",
        json={"order_id": "ORD-MVP-001", "amount": 99.5, "currency": "USD", "payment_method": "card"},
    )
    assert payment_response.status_code == 200
    assert payment_response.json()["status"] == "approved"
    transaction_id = payment_response.json()["transaction_id"]

    payment_status = client_payment.get(f"/payments/{transaction_id}")
    assert payment_status.status_code == 200
    assert payment_status.json()["transaction_id"] == transaction_id
    assert payment_status.json()["order_id"] == "ORD-MVP-001"

    # Tra cứu payment theo order_id
    by_order = client_payment.get("/payments/by-order/ORD-MVP-001")
    assert by_order.status_code == 200

    notification_response = client_notification.post(
        "/notifications",
        json={
            "channel": "email",
            "recipient": "alice@example.com",
            "message": "Order confirmed",
            "event_type": "order_paid",
        },
    )
    assert notification_response.status_code == 200
    notification_id = notification_response.json()["notification_id"]
    assert notification_response.json()["event_type"] == "order_paid"

    notification_status = client_notification.get(f"/notifications/{notification_id}")
    assert notification_status.status_code == 200
    assert notification_status.json()["notification_id"] == notification_id
