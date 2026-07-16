# Project page URL

https://roadmap.sh/projects/scalable-ecommerce-platform

# Scalable E-Commerce Platform

A production-grade microservices e-commerce platform built with **FastAPI**, **Docker**, **Kubernetes**, **Redis**, and **Consul**.  
Features service discovery, database migrations, centralized caching, RBAC authorization, standardized error handling, centralized logging, real-time metrics, automated CI/CD, and container orchestration.

---

## 🏗️ Architecture Overview

```
Client (Postman / Browser)
        │
        ▼
┌───────────────────┐
│   API Gateway     │  :9000  ← Single entry point, dynamic routing, Swagger docs proxy
└───────┬───────────┘
        │  Discovers service addresses from Consul
        ▼
┌───────────────────────────────────────────────────────────┐
│                   Consul Service Registry  :8500           │
└───────────────────────────────────────────────────────────┘
        │
        ├── User Service          :8000  (users_db)        ← JWT, Refresh Token Rotation
        ├── Product Service       :8001  (products_db)     ← Caching via Redis
        ├── Cart Service          :8002  (carts_db)
        ├── Order Service         :8003  (orders_db)
        ├── Payment Service       :8004  (payments_db)
        └── Notification Service  :8005  (notifications_db)
                │
                ├── PostgreSQL :5432  (6 databases on one Postgres instance)
                └── Redis      :6379  (Product catalog caching)

Monitoring & Logging:
  Prometheus  :9090  ← scrapes /metrics from all 7 services
  Grafana     :3000  ← dashboards for metrics + Loki logs
  Loki        :3100  ← log aggregation
  Promtail           ← tails ./logs/*.log → pushes to Loki
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Framework** | FastAPI 0.111.0 |
| **Runtime** | Python 3.11-slim, Uvicorn 0.30.0 |
| **Database** | PostgreSQL 16 (database-per-service pattern) |
| **Cache** | Redis 7 (Alpine) |
| **ORM & Migrations** | SQLAlchemy 2.x + Alembic (Database schema migrations) |
| **Service Discovery** | Consul 1.16 |
| **Security & Auth** | JWT (python-jose) + Refresh Token Rotation + RBAC (User/Admin) |
| **Monitoring** | Prometheus + Grafana + Loki + Promtail |
| **Orchestration** | Docker Compose / Kubernetes |
| **CI/CD** | GitHub Actions (pytest on push/PR to main) |
| **Testing** | Pytest 8.3.2 (**125 test cases** - 100% green) |

---

## 🚀 Quick Start — Docker Compose (Recommended)

### 1. Clone & Start

```bash
git clone https://github.com/Bui-Tien-Dat-2808/Scalable-E-Commerce-Platform.git
cd Scalable-E-Commerce-Platform

docker compose up --build -d
```

### 2. Verify all services are running

```bash
docker compose ps
```
Expected: all 14 containers (including `redis`) showing `Up` / `Up (healthy)`.

### 3. Access URLs
```
API Gateway (Entrypoint): http://localhost:9000
Consul UI:               http://localhost:8500
Prometheus UI:           http://localhost:9090
Grafana UI:              http://localhost:3000  (admin / admin)
```

### 4. Stop

```bash
docker compose down
```

> Data is **persisted** in the `postgres_data` Docker volume — restarting does not lose data.

---

## 📖 Swagger Documentation (API Specs)

Thanks to the Gateway dynamic routing, you can access the interactive Swagger UI of all individual microservices directly through the Gateway:

* **User Service Docs**: [http://localhost:9000/users/docs](http://localhost:9000/users/docs)
* **Product Service Docs**: [http://localhost:9000/products/docs](http://localhost:9000/products/docs)
* **Cart Service Docs**: [http://localhost:9000/cart/docs](http://localhost:9000/cart/docs)
* **Order Service Docs**: [http://localhost:9000/orders/docs](http://localhost:9000/orders/docs)
* **Payment Service Docs**: [http://localhost:9000/payments/docs](http://localhost:9000/payments/docs)
* **Notification Service Docs**: [http://localhost:9000/notifications/docs](http://localhost:9000/notifications/docs)

---

## 🔒 Security & Authorization

### 1. JWT & Refresh Token Rotation
* **Login** returns both `access_token` (expires in 15 mins) and `refresh_token` (expires in 7 days).
* The `refresh_token` is hashed (SHA-256) and stored in the database.
* **Refresh Token Rotation**: Utilizing the token rotation mechanism, refreshing an access token invalidates the old refresh token and issues a new one. Single-use refresh tokens prevent replay attacks.
* **Logout** blacklists/deletes the refresh token from the database.

### 2. Role-Based Access Control (RBAC)
User roles are classified as `user` or `admin`. 
* **User Endpoint Rules**: Regular users can manage their own profiles, carts, orders, and view products.
* **Admin Endpoint Rules**: Write operations in the Product Service (`POST /products`, `PUT /products/{id}`, `DELETE /products/{id}`) and listing/deleting users require the `admin` role.
* Default Admin account seeded at startup:
  * **Email**: `admin@example.com`
  * **Password**: `Admin123!`

---

## ⚡ Performance Optimization (Redis Caching)

* Endpoint `GET /products` is cached using Redis.
* **Cache Key**: Generated dynamically based on query params (page, limit, name, price range, stock status).
* **Cache Invalidation**: To ensure data consistency, the cache is automatically cleared when a product is created (`POST`), updated (`PUT`), deleted (`DELETE`), or when stock is deducted (`PATCH .../deduct-stock`).
* **Fallback Mode**: If Redis is offline, the service gracefully falls back to querying PostgreSQL directly, preventing any downtime.

---

## 🗄️ Database Migrations (Alembic)

Database schemas are managed using Alembic migrations in both `user-service` and `product-service` to enable zero-downtime database upgrades.

To run migrations programmatically during startup, the services check the `RUN_MIGRATIONS=true` environment variable (configured in `docker-compose.yml`). If false (e.g., during tests), SQLAlchemy falls back to `create_all()`.

Manual Alembic commands (run within the service folder):
```bash
# Generate a new migration
alembic revision --autogenerate -m "Add new column"

# Upgrade database to head
alembic upgrade head
```

---

## ❌ Global Standardized Errors

All services return errors in a unified format, making client consumption cleaner:
```json
{
  "error": {
    "code": "BAD_REQUEST",
    "message": "Details of the error occurred",
    "details": []
  }
}
```
Validation errors (HTTP 422) are captured globally and mapped to this schema, detailing exact field problems.

---

## 🔌 API Reference

All requests go through the API Gateway at `http://localhost:9000`.

### Health Checks
```
GET  /health                        → Gateway health
GET  /users/health                  → User Service
GET  /products/health               → Product Service
GET  /cart/health                   → Cart Service
GET  /orders/health                 → Order Service
GET  /payments/health               → Payment Service
GET  /notifications/health          → Notification Service
```

### User Service
```
POST   /users/auth/register         → Register new user
POST   /users/auth/login            → Login (returns access + refresh tokens)
POST   /users/auth/refresh          → Rotate refresh token to get a new access token
POST   /users/auth/logout           → Revoke refresh token
GET    /users                       * Admin only * List users (paginated)
GET    /users/{id}                  → View profile (self or admin)
PUT    /users/{id}                  → Update user profile (self or admin)
DELETE /users/{id}                  * Admin only * Delete user
```

### Product Service
```
GET    /products                    → List all active products (paginated, filtered, cached)
GET    /products/{id}               → Get product details by ID
POST   /products                    * Admin only * Create product
PUT    /products/{id}               * Admin only * Update product details
DELETE /products/{id}               * Admin only * Soft delete product
```

### Shopping Cart (Auth Required)
```
GET    /cart                        → View current user's cart items
POST   /cart/items                  → Add item to cart { product_id, quantity }
PUT    /cart/items/{product_id}     → Update item quantity (positive values only)
DELETE /cart/items/{product_id}     → Remove item from cart
```

### Order Service (Auth Required)
```
POST   /orders                      → Checkout cart & create order
GET    /orders                      → List current user's orders (paginated)
GET    /orders/{id}                 → Order detail
PATCH  /orders/{id}/cancel          → Cancel order (restores product inventory)
```

### Payment Service
```
POST   /payments/checkout           → Process payment { order_id, amount, payment_method }
GET    /payments/{transaction_id}   → Get payment by transaction ID
GET    /payments/order/{order_id}   → Get payment by order ID
```

### Notification Service
```
POST   /notifications               → Send custom notification
GET    /notifications/{id}          → View notification details
```

---

## 🧪 Testing

Tests run independently using SQLite in-memory databases and mocking external network dependencies.

### Running tests locally:
```bash
# Setup virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run all 125 test cases via virtualenv
.venv\Scripts\python -m pytest tests/ -v --tb=short
```

---

## ✅ Final Feature Checklist

- [x] **7 microservices** with FastAPI
- [x] **API Gateway** with dynamic Consul-based routing
- [x] **PostgreSQL** — database-per-service pattern (6 databases)
- [x] **Redis Caching** for Product Service catalog
- [x] **Alembic Migrations** for database schema management
- [x] **JWT Token Rotation** & Blacklisting
- [x] **Role-Based Access Control (RBAC)** (User / Admin)
- [x] **Pagination & Filtering** on endpoints
- [x] **Standardized Error Handling** (unified JSON payloads)
- [x] **Swagger UI integration** for all services via Gateway routing
- [x] **Prometheus metrics** (`/metrics` on all services)
- [x] **Centralized Logging & Monitoring** (Loki + Promtail + Grafana)
- [x] **125 automated tests** (100% passing)
- [x] **Kubernetes manifests** (Deployments, Services, PVC, ConfigMap, Secrets)
- [x] **Postman collection** for easy API testing (`docs/`)