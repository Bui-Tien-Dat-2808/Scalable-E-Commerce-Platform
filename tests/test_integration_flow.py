"""
Integration test: Full business flow
Order → Payment → Notification (in-process, các service dùng TestClient)
HTTP calls giữa các service được mock để simulate inter-service communication.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from services.user_service.app.main import app as user_app
from services.product_service.app.main import app as product_app, ProductModel
from services.cart_service.app.main import app as cart_app
from services.order_service.app.main import app as order_app
from services.payment_service.app.main import app as payment_app
from services.notification_service.app.main import app as notification_app
from services.common.database import Base, engine, SessionLocal


client_user = TestClient(user_app)
client_product = TestClient(product_app)
client_cart = TestClient(cart_app)
client_order = TestClient(order_app)
client_payment = TestClient(payment_app)
client_notification = TestClient(notification_app)


@pytest.fixture(autouse=True)
def reset_all():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    # Seed products cho integration test
    with SessionLocal() as db:
        db.add_all([
            ProductModel(id=1, name="Laptop", price=999.99, stock=10),
            ProductModel(id=2, name="Smartphone", price=499.99, stock=20),
        ])
        db.commit()
        
    yield
    Base.metadata.drop_all(bind=engine)


def _register_and_login(email: str, username: str, password: str = "secret123") -> dict:
    client_user.post("/auth/register", json={"username": username, "email": email, "password": password})
    resp = client_user.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_product_response(pid, name, price, stock):
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={"id": pid, "name": name, "price": price, "stock": stock, "is_active": True}),
    )


def _make_deduct_response(ok=True, product_id=1, deducted=1, remaining=9):
    if ok:
        return MagicMock(
            status_code=200,
            json=MagicMock(return_value={"product_id": product_id, "deducted": deducted, "remaining_stock": remaining}),
        )
    return MagicMock(
        status_code=409,
        json=MagicMock(return_value={"detail": f"Insufficient stock for product {product_id}"}),
    )


def _make_payment_response(order_ref, amount, approved=True):
    txn_id = "TXN-INTTEST01"
    status = "approved" if approved else "failed"
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={"transaction_id": txn_id, "order_id": order_ref, "amount": amount, "status": status}),
    )


def _make_notification_response():
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={"notification_id": "NTF-INTTEST01", "status": "queued"}),
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestFullOrderFlow:
    def test_user_registers_adds_to_cart_places_order_gets_paid(self):
        """
        Luồng đầy đủ:
        1. User đăng ký & đăng nhập
        2. Thêm sản phẩm vào giỏ hàng
        3. Tạo order → payment approved → status = paid
        4. Notification được gửi
        """
        headers = _register_and_login("alice@test.com", "alice")

        # Bước 2: Thêm vào giỏ
        cart_resp = client_cart.post("/cart/items", json={"product_id": 1, "quantity": 2}, headers=headers)
        assert cart_resp.status_code == 200
        cart = cart_resp.json()
        assert any(i["product_id"] == 1 for i in cart["items"])

        # Bước 3: Tạo order (mock inter-service HTTP)
        with patch.multiple(
            "services.order_service.app.main.httpx",
            get=lambda url, **kw: _make_product_response(1, "Laptop", 999.99, 10),
            patch=lambda url, **kw: _make_deduct_response(ok=True, product_id=1, deducted=2, remaining=8),
            post=lambda url, **kw: (
                _make_payment_response("ORD-1", 1999.98, approved=True)
                if "payments" in url
                else _make_notification_response()
            ),
        ):
            order_resp = client_order.post(
                "/orders",
                json={
                    "items": [{"product_id": 1, "quantity": 2}],
                    "payment_method": "card",
                    "recipient_email": "alice@test.com",
                },
                headers=headers,
            )

        assert order_resp.status_code == 201, order_resp.json()
        order = order_resp.json()
        assert order["status"] == "paid"
        assert order["transaction_id"] == "TXN-INTTEST01"
        assert order["total_amount"] == pytest.approx(1999.98, abs=0.01)

        # Bước 4: Verify order trong order list
        list_resp = client_order.get("/orders", headers=headers)
        assert list_resp.status_code == 200
        assert any(o["order_id"] == order["order_id"] for o in list_resp.json()["data"])

    def test_order_payment_failed_status_reflects_failure(self):
        """If payment fail, order status = failed_payment."""
        headers = _register_and_login("bob@test.com", "bob")

        with patch.multiple(
            "services.order_service.app.main.httpx",
            get=lambda url, **kw: _make_product_response(1, "Laptop", 999.99, 5),
            patch=lambda url, **kw: _make_deduct_response(ok=True),
            post=lambda url, **kw: (
                _make_payment_response("ORD-1", 999.99, approved=False)
                if "payments" in url
                else _make_notification_response()
            ),
        ):
            resp = client_order.post(
                "/orders",
                json={"items": [{"product_id": 1, "quantity": 1}], "payment_method": "fail"},
                headers=headers,
            )

        assert resp.status_code == 201
        assert resp.json()["status"] == "failed_payment"
        assert resp.json()["payment_status"] == "failed"

    def test_order_insufficient_stock_rejected(self):
        """Order bị từ chối nếu stock không đủ."""
        headers = _register_and_login("carol@test.com", "carol")

        with patch.multiple(
            "services.order_service.app.main.httpx",
            get=lambda url, **kw: _make_product_response(1, "Laptop", 999.99, 1),
            patch=lambda url, **kw: _make_deduct_response(ok=False, product_id=1),
            post=lambda url, **kw: _make_payment_response("ORD-1", 0),
        ):
            resp = client_order.post(
                "/orders",
                json={"items": [{"product_id": 1, "quantity": 5}]},
                headers=headers,
            )

        assert resp.status_code == 400
        assert "stock" in resp.json()["detail"].lower()

    def test_cancel_order_changes_status(self):
        """User có thể cancel order, status = cancelled."""
        headers = _register_and_login("dave@test.com", "dave")

        with patch.multiple(
            "services.order_service.app.main.httpx",
            get=lambda url, **kw: _make_product_response(2, "Smartphone", 499.99, 10),
            patch=lambda url, **kw: _make_deduct_response(ok=True, product_id=2),
            post=lambda url, **kw: (
                _make_payment_response("ORD-1", 499.99, approved=True)
                if "payments" in url
                else _make_notification_response()
            ),
        ):
            create_resp = client_order.post(
                "/orders",
                json={"items": [{"product_id": 2, "quantity": 1}]},
                headers=headers,
            )
        order_id = create_resp.json()["id"]

        with patch("services.order_service.app.main.httpx.post", return_value=_make_notification_response()):
            cancel_resp = client_order.patch(f"/orders/{order_id}/cancel", headers=headers)

        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

    def test_two_users_orders_are_isolated(self):
        """Hai user không thấy order của nhau."""
        headers_a = _register_and_login("alice2@test.com", "alice2")
        headers_b = _register_and_login("bob2@test.com", "bob2")

        with patch.multiple(
            "services.order_service.app.main.httpx",
            get=lambda url, **kw: _make_product_response(1, "Laptop", 999.99, 10),
            patch=lambda url, **kw: _make_deduct_response(),
            post=lambda url, **kw: (
                _make_payment_response("ORD-1", 999.99) if "payments" in url else _make_notification_response()
            ),
        ):
            client_order.post("/orders", json={"items": [{"product_id": 1, "quantity": 1}]}, headers=headers_a)

        orders_a = client_order.get("/orders", headers=headers_a).json()["data"]
        orders_b = client_order.get("/orders", headers=headers_b).json()["data"]

        assert len(orders_a) == 1
        assert len(orders_b) == 0
