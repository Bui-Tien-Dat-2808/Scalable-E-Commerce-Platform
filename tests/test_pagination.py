"""
Pagination & Filtering Tests — tests for GET /products and GET /orders.
"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from services.user_service.app.main import app as user_app
from services.product_service.app.main import app as product_app, ProductModel
from services.order_service.app.main import app as order_app
from services.common.database import Base, engine, SessionLocal

client_user = TestClient(user_app)
client_product = TestClient(product_app)
client_order = TestClient(order_app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Seed 5 products with different names and prices
    with SessionLocal() as db:
        db.add_all([
            ProductModel(name="Laptop", price=999.99, stock=10),
            ProductModel(name="Smartphone", price=499.99, stock=20),
            ProductModel(name="Tablet", price=299.99, stock=0),   # out of stock
            ProductModel(name="Monitor", price=350.00, stock=5),
            ProductModel(name="Keyboard", price=79.99, stock=15),
        ])
        db.commit()
    yield
    Base.metadata.drop_all(bind=engine)


def _auth_headers() -> dict:
    client_user.post("/auth/register", json={
        "username": "paginationuser",
        "email": "page@test.com",
        "password": "PagePass123!",
    })
    resp = client_user.post("/auth/login", json={
        "email": "page@test.com",
        "password": "PagePass123!",
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── GET /products — Pagination ────────────────────────────────────────────────

def test_products_pagination_default():
    """Default: page=1, limit=20 — returns all 5 products."""
    resp = client_product.get("/products")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "total" in body
    assert "page" in body
    assert "limit" in body
    assert "pages" in body
    assert body["page"] == 1
    assert body["limit"] == 20
    assert body["total"] == 5


def test_products_pagination_limit_1():
    """Limit to 1 item per page — returns 1 product, pages=5."""
    resp = client_product.get("/products?page=1&limit=1")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["pages"] == 5
    assert body["total"] == 5


def test_products_pagination_page_2():
    """Page 2 with limit=2 — returns 2 products (items 3-4)."""
    resp = client_product.get("/products?page=2&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["page"] == 2


def test_products_pagination_out_of_range():
    """Page out of range — returns empty data, total is still correct."""
    resp = client_product.get("/products?page=99&limit=20")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 0
    assert body["total"] == 5


# ── GET /products — Filtering ─────────────────────────────────────────────────

def test_products_filter_by_name_exact():
    """Filter by name 'Laptop' — returns exactly 1 product."""
    resp = client_product.get("/products?name=Laptop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["name"] == "Laptop"


def test_products_filter_by_name_partial():
    """Filter by partial name 'top' — matches 'Laptop'."""
    resp = client_product.get("/products?name=top")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert any("top" in p["name"].lower() for p in resp.json()["data"])


def test_products_filter_by_min_price():
    """Filter by price >= 500 — only matches Laptop (999.99)."""
    resp = client_product.get("/products?min_price=500")
    assert resp.status_code == 200
    assert all(p["price"] >= 500 for p in resp.json()["data"])


def test_products_filter_by_max_price():
    """Filter by price <= 100 — only matches Keyboard (79.99)."""
    resp = client_product.get("/products?max_price=100")
    assert resp.status_code == 200
    assert all(p["price"] <= 100 for p in resp.json()["data"])


def test_products_filter_by_price_range():
    """Filter by 300 <= price <= 500 — matches Smartphone (499.99) and Monitor (350)."""
    resp = client_product.get("/products?min_price=300&max_price=500")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(300 <= p["price"] <= 500 for p in data)


def test_products_filter_in_stock_true():
    """in_stock=true — does not return out-of-stock Tablet."""
    resp = client_product.get("/products?in_stock=true")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(p["stock"] > 0 for p in data)
    assert not any(p["name"] == "Tablet" for p in data)


def test_products_filter_in_stock_false():
    """in_stock=false — only returns out-of-stock Tablet."""
    resp = client_product.get("/products?in_stock=false")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(p["stock"] == 0 for p in data)
    assert any(p["name"] == "Tablet" for p in data)


def test_products_combine_filters():
    """Combine name + min_price — returns correct intersection."""
    resp = client_product.get("/products?name=Monitor&min_price=300")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Monitor"


# ── GET /orders — Pagination + Filtering ──────────────────────────────────────

def test_orders_pagination_empty():
    """New user with no orders — returns total=0, data=[]."""
    headers = _auth_headers()
    resp = client_order.get("/orders", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["data"] == []
    assert body["page"] == 1


def test_orders_pagination_structure():
    """Verify response structure contains all pagination fields."""
    headers = _auth_headers()
    resp = client_order.get("/orders?page=1&limit=10", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "total" in body
    assert "page" in body
    assert "limit" in body
    assert "pages" in body
    assert body["limit"] == 10


def test_orders_filter_by_status_no_match():
    """Filter by status='paid' when no orders exist — returns empty list."""
    headers = _auth_headers()
    resp = client_order.get("/orders?status=paid", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["data"] == []


def test_orders_with_created_order_pagination():
    """Create actual order → check pagination results."""
    headers = _auth_headers()

    mock_product = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"id": 1, "name": "Laptop", "price": 999.99, "stock": 10, "is_active": True}),
    )
    mock_deduct = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"product_id": 1, "deducted": 1, "remaining_stock": 9}),
    )
    mock_payment = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"transaction_id": "TXN-PAG01", "order_id": "ORD-1", "amount": 999.99, "status": "approved"}),
    )
    mock_notify = MagicMock(status_code=200, json=MagicMock(return_value={}))

    with patch.multiple(
        "services.order_service.app.main.httpx",
        get=lambda url, **kw: mock_product,
        patch=lambda url, **kw: mock_deduct,
        post=lambda url, **kw: mock_payment if "payments" in url else mock_notify,
    ):
        client_order.post(
            "/orders",
            json={"items": [{"product_id": 1, "quantity": 1}], "payment_method": "card"},
            headers=headers,
        )

    resp = client_order.get("/orders", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["status"] == "paid"


def test_orders_filter_by_status_paid():
    """After creating paid order → filter status=paid returns exactly 1 record."""
    headers = _auth_headers()

    mock_product = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"id": 1, "name": "Laptop", "price": 999.99, "stock": 10, "is_active": True}),
    )
    mock_deduct = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"product_id": 1, "deducted": 1, "remaining_stock": 9}),
    )
    mock_payment = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"transaction_id": "TXN-PAG02", "order_id": "ORD-1", "amount": 999.99, "status": "approved"}),
    )
    mock_notify = MagicMock(status_code=200, json=MagicMock(return_value={}))

    with patch.multiple(
        "services.order_service.app.main.httpx",
        get=lambda url, **kw: mock_product,
        patch=lambda url, **kw: mock_deduct,
        post=lambda url, **kw: mock_payment if "payments" in url else mock_notify,
    ):
        client_order.post(
            "/orders",
            json={"items": [{"product_id": 1, "quantity": 1}], "payment_method": "card"},
            headers=headers,
        )

    # Filter status=paid
    resp_paid = client_order.get("/orders?status=paid", headers=headers)
    assert resp_paid.json()["total"] == 1

    # Filter status=cancelled — should be empty
    resp_cancelled = client_order.get("/orders?status=cancelled", headers=headers)
    assert resp_cancelled.json()["total"] == 0
