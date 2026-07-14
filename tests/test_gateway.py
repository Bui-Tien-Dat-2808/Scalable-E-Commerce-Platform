"""Unit tests for API Gateway."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import api_gateway
from api_gateway import app


client = TestClient(app)


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._payload


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, params=None, content=None, headers=None):
        return DummyResponse({"ok": True, "method": method, "url": url}, status_code=200)


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_gateway_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "api-gateway"


def test_gateway_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "api-gateway"


def test_gateway_proxies_post(monkeypatch):
    class PostAsyncClient(DummyAsyncClient):
        async def request(self, method, url, **kwargs):
            return DummyResponse({"ok": True, "method": method, "url": url}, status_code=201)

    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", PostAsyncClient)
    response = client.post("/users/register", json={"username": "alice"})
    assert response.status_code == 201
    assert response.json()["ok"] is True


def test_gateway_proxies_get(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.get("/products")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_gateway_proxies_patch(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.patch("/orders/1/cancel")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_gateway_proxies_delete(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.delete("/products/1")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_gateway_unknown_service_returns_404():
    response = client.get("/unknownservice/something")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_gateway_routes_users(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.get("/users")
    assert response.status_code == 200


def test_gateway_routes_cart(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.get("/cart")
    assert response.status_code == 200


def test_gateway_routes_orders(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.get("/orders")
    assert response.status_code == 200


def test_gateway_routes_payments(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.get("/payments")
    assert response.status_code == 200


def test_gateway_routes_notifications(monkeypatch):
    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", DummyAsyncClient)
    response = client.get("/notifications")
    assert response.status_code == 200


def test_gateway_forwards_auth_header(monkeypatch):
    captured = {}

    class CapturingClient(DummyAsyncClient):
        async def request(self, method, url, headers=None, **kwargs):
            captured["headers"] = headers or {}
            return DummyResponse({"ok": True})

    monkeypatch.setattr(api_gateway.httpx, "AsyncClient", CapturingClient)
    client.get("/orders", headers={"Authorization": "Bearer test-token"})
    assert "authorization" in captured.get("headers", {})
