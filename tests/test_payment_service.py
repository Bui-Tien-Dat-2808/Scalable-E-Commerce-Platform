"""Unit tests for Payment Service."""
import pytest
from fastapi.testclient import TestClient

from services.payment_service.app.main import app, payments_db, payments_by_order


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_state():
    payments_db.clear()
    payments_by_order.clear()
    yield
    payments_db.clear()
    payments_by_order.clear()


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_checkout_approved():
    resp = client.post(
        "/payments/checkout",
        json={"order_id": "ORD-1", "amount": 99.99, "currency": "USD", "payment_method": "card"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["order_id"] == "ORD-1"
    assert data["amount"] == 99.99
    assert data["transaction_id"].startswith("TXN-")


def test_checkout_failed_zero_amount():
    resp = client.post(
        "/payments/checkout",
        json={"order_id": "ORD-2", "amount": 0.0, "currency": "USD", "payment_method": "card"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


def test_checkout_failed_payment_method_declined():
    resp = client.post(
        "/payments/checkout",
        json={"order_id": "ORD-3", "amount": 50.0, "currency": "USD", "payment_method": "declined"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


def test_checkout_failed_payment_method_fail():
    resp = client.post(
        "/payments/checkout",
        json={"order_id": "ORD-4", "amount": 50.0, "currency": "USD", "payment_method": "fail"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"


def test_checkout_stores_order_id():
    resp = client.post(
        "/payments/checkout",
        json={"order_id": "ORD-10", "amount": 200.0, "currency": "USD", "payment_method": "card"},
    )
    assert resp.status_code == 200
    txn_id = resp.json()["transaction_id"]

    # Lấy payment theo transaction_id
    get_resp = client.get(f"/payments/{txn_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["order_id"] == "ORD-10"


def test_get_payment_by_transaction_id():
    checkout = client.post(
        "/payments/checkout",
        json={"order_id": "ORD-5", "amount": 49.0, "currency": "EUR", "payment_method": "card"},
    )
    txn_id = checkout.json()["transaction_id"]

    resp = client.get(f"/payments/{txn_id}")
    assert resp.status_code == 200
    assert resp.json()["transaction_id"] == txn_id


def test_get_payment_by_order_id():
    client.post(
        "/payments/checkout",
        json={"order_id": "ORD-6", "amount": 75.0, "currency": "USD", "payment_method": "card"},
    )
    resp = client.get("/payments/by-order/ORD-6")
    assert resp.status_code == 200
    assert resp.json()["order_id"] == "ORD-6"


def test_get_payment_not_found():
    resp = client.get("/payments/TXN-NONEXISTENT")
    assert resp.status_code == 404


def test_get_payment_by_order_not_found():
    resp = client.get("/payments/by-order/ORD-NONEXISTENT")
    assert resp.status_code == 404


def test_transaction_id_is_unique():
    r1 = client.post("/payments/checkout", json={"order_id": "ORD-A", "amount": 10.0, "payment_method": "card"})
    r2 = client.post("/payments/checkout", json={"order_id": "ORD-B", "amount": 20.0, "payment_method": "card"})
    assert r1.json()["transaction_id"] != r2.json()["transaction_id"]
