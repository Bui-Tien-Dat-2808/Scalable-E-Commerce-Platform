"""
Pagination & Filtering Tests — kiểm tra GET /products và GET /orders.
"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from services.user_service.app.main import app as user_app, UserModel
from services.product_service.app.main import app as product_app, ProductModel
from services.order_service.app.main import app as order_app
from services.common.database import Base, engine, SessionLocal
from services.common.security import hash_password

client_user = TestClient(user_app)
client_product = TestClient(product_app)
client_order = TestClient(order_app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Seed 5 sản phẩm với giá và tên khác nhau
    with SessionLocal() as db:
        db.add_all([
            ProductModel(name="Laptop", price=999.99, stock=10),
            ProductModel(name="Smartphone", price=499.99, stock=20),
            ProductModel(name="Tablet", price=299.99, stock=0),   # hết hàng
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
    """Mặc định: page=1, limit=20 — trả về tất cả 5 sản phẩm."""
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
    """Giới hạn 1 item mỗi trang — trả về 1 sản phẩm, pages=5."""
    resp = client_product.get("/products?page=1&limit=1")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["pages"] == 5
    assert body["total"] == 5


def test_products_pagination_page_2():
    """Trang 2 với limit=2 — trả về 2 sản phẩm (item 3-4)."""
    resp = client_product.get("/products?page=2&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["page"] == 2


def test_products_pagination_out_of_range():
    """Trang vượt quá dữ liệu — trả về data rỗng, total vẫn đúng."""
    resp = client_product.get("/products?page=99&limit=20")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 0
    assert body["total"] == 5


# ── GET /products — Filtering ─────────────────────────────────────────────────

def test_products_filter_by_name_exact():
    """Lọc theo tên 'Laptop' — trả về đúng 1 sản phẩm."""
    resp = client_product.get("/products?name=Laptop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["name"] == "Laptop"


def test_products_filter_by_name_partial():
    """Lọc tên gần đúng 'top' — match 'Laptop'."""
    resp = client_product.get("/products?name=top")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    assert any("top" in p["name"].lower() for p in resp.json()["data"])


def test_products_filter_by_min_price():
    """Lọc price >= 500 — chỉ Laptop (999.99) và Smartphone (499.99→ không pass vì <500)."""
    resp = client_product.get("/products?min_price=500")
    assert resp.status_code == 200
    assert all(p["price"] >= 500 for p in resp.json()["data"])


def test_products_filter_by_max_price():
    """Lọc price <= 100 — chỉ Keyboard (79.99)."""
    resp = client_product.get("/products?max_price=100")
    assert resp.status_code == 200
    assert all(p["price"] <= 100 for p in resp.json()["data"])


def test_products_filter_by_price_range():
    """Lọc 300 <= price <= 500 — Smartphone (499.99), Tablet (299.99→ không pass), Monitor (350)."""
    resp = client_product.get("/products?min_price=300&max_price=500")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(300 <= p["price"] <= 500 for p in data)


def test_products_filter_in_stock_true():
    """in_stock=true — không trả về Tablet (stock=0)."""
    resp = client_product.get("/products?in_stock=true")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(p["stock"] > 0 for p in data)
    assert not any(p["name"] == "Tablet" for p in data)


def test_products_filter_in_stock_false():
    """in_stock=false — chỉ trả về Tablet (stock=0)."""
    resp = client_product.get("/products?in_stock=false")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert all(p["stock"] == 0 for p in data)
    assert any(p["name"] == "Tablet" for p in data)


def test_products_combine_filters():
    """Kết hợp name + min_price — phải trả về đúng kết quả intersection."""
    resp = client_product.get("/products?name=Monitor&min_price=300")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Monitor"


# ── GET /orders — Pagination + Filtering ──────────────────────────────────────

def test_orders_pagination_empty():
    """User mới chưa có order — trả về total=0, data=[]."""
    headers = _auth_headers()
    resp = client_order.get("/orders", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["data"] == []
    assert body["page"] == 1


def test_orders_pagination_structure():
    """Kiểm tra cấu trúc response có đủ fields pagination."""
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
    """Lọc theo status='paid' khi chưa có order nào — trả về rỗng."""
    headers = _auth_headers()
    resp = client_order.get("/orders?status=paid", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["data"] == []


def test_orders_with_created_order_pagination():
    """Tạo order thật → kiểm tra pagination trả về đúng."""
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
    """Sau khi tạo order paid → filter status=paid trả về đúng 1 record."""
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

    # Filter status=cancelled — không có
    resp_cancelled = client_order.get("/orders?status=cancelled", headers=headers)
    assert resp_cancelled.json()["total"] == 0
