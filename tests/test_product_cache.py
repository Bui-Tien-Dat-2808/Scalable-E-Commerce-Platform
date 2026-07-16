import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from services.product_service.app.main import app
from services.user_service.app.main import app as user_app, UserModel
from services.common.database import Base, engine, SessionLocal
from services.common.security import hash_password


client = TestClient(app)
client_user = TestClient(user_app)


# ── Fake Redis Mock ───────────────────────────────────────────────────────────

class FakeRedis:
    def __init__(self):
        self.store = {}
        self.calls = {
            "get": 0,
            "setex": 0,
            "delete": 0
        }

    def get(self, key):
        self.calls["get"] += 1
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.calls["setex"] += 1
        self.store[key] = value

    def keys(self, pattern):
        prefix = pattern.split("*")[0]
        return [k for k in self.store.keys() if k.startswith(prefix)]

    def delete(self, *keys):
        self.calls["delete"] += 1
        for k in keys:
            self.store.pop(k, None)


@pytest.fixture
def fake_redis():
    fake = FakeRedis()
    with patch("services.product_service.app.main.redis_client", fake):
        yield fake


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _admin_headers() -> dict:
    """Create realistic admin headers by logging in via user_service."""
    with SessionLocal() as db:
        admin = db.query(UserModel).filter(UserModel.email == "admin@test.com").first()
        if not admin:
            db.add(UserModel(
                username="admin",
                email="admin@test.com",
                password=hash_password("AdminPass123!"),
                role="admin"
            ))
            db.commit()
    resp = client_user.post("/auth/login", json={"email": "admin@test.com", "password": "AdminPass123!"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_cache_miss_then_cache_hit(fake_redis):
    # Call 1: Fetch list (empty DB) -> Cache Miss
    resp1 = client.get("/products")
    assert resp1.status_code == 200
    assert resp1.json()["total"] == 0
    assert fake_redis.calls["get"] == 1
    assert fake_redis.calls["setex"] == 1

    # Create product directly in DB (bypass API to avoid cache invalidation)
    from services.product_service.app.main import ProductModel
    with SessionLocal() as db:
        db.add(ProductModel(name="Secret Product", price=100.0, stock=10))
        db.commit()

    # Call 2: Call again -> Cache Hit -> Must still return empty list (since cache stored empty list)
    resp2 = client.get("/products")
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 0  # Still 0 due to cache hit
    assert fake_redis.calls["get"] == 2
    assert fake_redis.calls["setex"] == 1  # Did not increase because it was fetched from cache


def test_create_product_invalidates_cache(fake_redis):
    # Call 1: Call to populate cache
    client.get("/products")
    assert len(fake_redis.store) > 0  # Cache key exists

    # Call 2: Admin creates product -> Must invalidate cache
    headers = _admin_headers()
    payload = {"name": "New Phone", "price": 999.0, "stock": 50}
    resp = client.post("/products", json=payload, headers=headers)
    assert resp.status_code == 201
    
    # Verify cache is fully invalidated
    assert len(fake_redis.store) == 0
    assert fake_redis.calls["delete"] == 1


def test_update_product_invalidates_cache(fake_redis):
    # Pre-create a product
    headers = _admin_headers()
    prod = client.post("/products", json={"name": "P1", "price": 10.0, "stock": 5}, headers=headers).json()
    prod_id = prod["id"]

    # Call list to populate cache
    client.get("/products")
    assert len(fake_redis.store) > 0

    # Update product -> Invalidate cache
    update_payload = {"name": "P1 Updated", "price": 15.0, "stock": 10}
    client.put(f"/products/{prod_id}", json=update_payload, headers=headers)

    # Verify cache is fully invalidated
    assert len(fake_redis.store) == 0


def test_delete_product_invalidates_cache(fake_redis):
    # Pre-create a product
    headers = _admin_headers()
    prod = client.post("/products", json={"name": "P1", "price": 10.0, "stock": 5}, headers=headers).json()
    prod_id = prod["id"]

    # Call list to populate cache
    client.get("/products")
    assert len(fake_redis.store) > 0

    # Delete product -> Invalidate cache
    client.delete(f"/products/{prod_id}", headers=headers)

    # Verify cache is fully invalidated
    assert len(fake_redis.store) == 0
