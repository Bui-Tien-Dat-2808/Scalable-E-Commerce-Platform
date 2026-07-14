"""Unit tests for Notification Service."""
import pytest
from fastapi.testclient import TestClient

from services.notification_service.app.main import app, notifications_db


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_state():
    notifications_db.clear()
    yield
    notifications_db.clear()


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_email_notification():
    resp = client.post(
        "/notifications",
        json={
            "channel": "email",
            "recipient": "alice@example.com",
            "subject": "Order Confirmed",
            "message": "Your order has been placed.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["channel"] == "email"
    assert data["recipient"] == "alice@example.com"
    assert data["notification_id"].startswith("NTF-")


def test_create_notification_with_event_type():
    resp = client.post(
        "/notifications",
        json={
            "channel": "email",
            "recipient": "bob@example.com",
            "subject": "Payment Successful",
            "message": "Your payment was approved.",
            "event_type": "order_paid",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_type"] == "order_paid"
    assert data["status"] == "queued"


def test_create_notification_order_failed_event():
    resp = client.post(
        "/notifications",
        json={
            "channel": "email",
            "recipient": "carol@example.com",
            "message": "Payment failed.",
            "event_type": "order_failed",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "order_failed"


def test_create_notification_order_cancelled_event():
    resp = client.post(
        "/notifications",
        json={
            "channel": "sms",
            "recipient": "+84901234567",
            "message": "Your order has been cancelled.",
            "event_type": "order_cancelled",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["channel"] == "sms"
    assert data["event_type"] == "order_cancelled"


def test_create_notification_without_event_type_defaults_none():
    resp = client.post(
        "/notifications",
        json={
            "channel": "email",
            "recipient": "dave@example.com",
            "message": "Hello Dave",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] is None


def test_get_notification():
    create = client.post(
        "/notifications",
        json={"channel": "email", "recipient": "eve@example.com", "message": "Test message"},
    )
    ntf_id = create.json()["notification_id"]

    resp = client.get(f"/notifications/{ntf_id}")
    assert resp.status_code == 200
    assert resp.json()["notification_id"] == ntf_id


def test_notification_not_found():
    resp = client.get("/notifications/NTF-DOESNOTEXIST")
    assert resp.status_code == 404


def test_notification_id_is_unique():
    r1 = client.post("/notifications", json={"recipient": "a@x.com", "message": "msg1"})
    r2 = client.post("/notifications", json={"recipient": "b@x.com", "message": "msg2"})
    assert r1.json()["notification_id"] != r2.json()["notification_id"]


def test_multiple_notifications_stored():
    for i in range(3):
        client.post(
            "/notifications",
            json={"recipient": f"user{i}@example.com", "message": f"Message {i}"},
        )
    assert len(notifications_db) == 3
