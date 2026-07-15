# Scalable E-Commerce Platform

A production-grade microservices e-commerce platform built with **FastAPI**, **Docker**, and **Kubernetes**.  
Features service discovery, centralized logging, real-time metrics, persistent storage, automated CI/CD, and container orchestration.

---

## 🏗️ Architecture Overview

```
Client (Postman / Browser)
        │
        ▼
┌───────────────────┐
│   API Gateway     │  :9000  ← single entry point, dynamic routing via Consul
└───────┬───────────┘
        │  discovers service addresses from Consul
        ▼
┌───────────────────────────────────────────────────────────┐
│                   Consul Service Registry  :8500           │
└───────────────────────────────────────────────────────────┘
        │
        ├── User Service          :8000  (users_db)
        ├── Product Service       :8001  (products_db)
        ├── Cart Service          :8002  (carts_db)
        ├── Order Service         :8003  (orders_db)
        ├── Payment Service       :8004  (payments_db)
        └── Notification Service  :8005  (notifications_db)
                │
                ▼
        PostgreSQL :5432  (6 separate databases on one instance)

Monitoring Stack:
  Prometheus  :9090  ← scrapes /metrics from all 7 services
  Grafana     :3000  ← dashboards for metrics + logs
  Loki        :3100  ← log aggregation
  Promtail           ← tails ./logs/*.log → pushes to Loki
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.111.0 |
| Runtime | Python 3.11-slim, Uvicorn 0.30.0 |
| Database | PostgreSQL 16 (database-per-service) |
| ORM | SQLAlchemy 2.x + psycopg2-binary |
| Service Discovery | Consul 1.16 |
| Monitoring | Prometheus + Grafana + Loki + Promtail |
| Orchestration | Docker Compose / Kubernetes |
| CI/CD | GitHub Actions (pytest on push/PR) |
| Testing | Pytest 8.3.2 (77 test cases) |
| Auth | JWT (python-jose) |

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

Expected: all 13 containers showing `Up` / `Up (healthy)`.

### 3. Test via API Gateway

```
API Gateway:          http://localhost:9000
Consul UI:            http://localhost:8500
Prometheus UI:        http://localhost:9090
Grafana UI:           http://localhost:3000  (admin / admin)
```

### 4. Import Postman Collection

Import `docs/ECommerce_Platform.postman_collection.json` into Postman.  
Set Collection variable `base_url = http://localhost:9000` and run requests in order.

### 5. Stop

```bash
docker compose down
```

> Data is **persisted** in the `postgres_data` Docker volume — restarting does NOT lose data.

---

## ☸️ Kubernetes Deployment (Docker Desktop)

### Prerequisites
- Docker Desktop with **Kubernetes enabled** (Settings → Kubernetes → Enable Kubernetes)

### Deploy

```bash
# Apply all manifests
kubectl apply -f k8s/

# Watch pods come up
kubectl get pods -w
```

### Access API Gateway on Kubernetes

**Option A — Port Forward (reliable on Windows/WSL2):**
```bash
kubectl port-forward service/api-gateway-service 9000:9000
```
Then use `http://localhost:9000` in Postman as normal.

**Option B — NodePort (may require cluster reset on Windows):**
```
http://localhost:30000
```
> If NodePort `:30000` returns `ECONNREFUSED`, use port-forward (Option A) instead.  
> To fix NodePort: Docker Desktop → Settings → Kubernetes → **Reset Kubernetes Cluster** → `kubectl apply -f k8s/`

### Kubernetes Architecture

Each microservice Deployment uses the **Downward API** to inject Pod IP into Consul registration:
```yaml
env:
  - name: SERVICE_HOST
    valueFrom:
      fieldRef:
        fieldPath: status.podIP
```
This ensures Consul always has the correct Pod IP even when K8s reschedules pods.

### Teardown

```bash
kubectl delete -f k8s/
```

---

## 📁 Project Structure

```
.
├── api_gateway.py                  # API Gateway — dynamic routing via Consul
├── docker-compose.yml              # Full stack: 7 services + Postgres + Consul + LGP
├── Dockerfile                      # Single image for all Python services
├── init-multiple-databases.sh      # Creates 6 PostgreSQL databases on startup
├── requirements.txt                # Python dependencies
├── README.md
│
├── services/
│   ├── common/
│   │   ├── consul.py               # Consul register/deregister + static fallback
│   │   ├── database.py             # SQLAlchemy engine + session factory
│   │   ├── logging.py              # Shared RotatingFileHandler logger
│   │   └── security.py            # JWT encode/decode helpers
│   ├── user_service/app/main.py
│   ├── product_service/app/main.py
│   ├── cart_service/app/main.py
│   ├── order_service/app/main.py
│   ├── payment_service/app/main.py
│   └── notification_service/app/main.py
│
├── tests/                          # 77 test cases — run independently (SQLite in-memory)
│   ├── test_user_service.py
│   ├── test_product_service.py     # (via test_mvp_flow.py)
│   ├── test_cart_service.py
│   ├── test_order_service.py
│   ├── test_payment_service.py
│   ├── test_notification_service.py
│   ├── test_gateway.py
│   ├── test_mvp_flow.py
│   └── test_integration_flow.py
│
├── k8s/                            # Kubernetes manifests
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── postgres.yaml               # Deployment + PVC + Service
│   ├── db-init-configmap.yaml      # Init script for 6 databases
│   ├── consul.yaml
│   ├── api-gateway.yaml            # NodePort :30000
│   ├── user-service.yaml
│   ├── product-service.yaml
│   ├── cart-service.yaml
│   ├── order-service.yaml
│   ├── payment-service.yaml
│   └── notification-service.yaml
│
├── monitoring/
│   ├── prometheus.yml              # Scrape config for all 7 /metrics endpoints
│   ├── promtail-config.yml         # Tail ./logs/*.log → push to Loki
│   └── grafana/
│       └── provisioning/
│           └── datasources/
│               └── datasources.yml # Auto-provision Prometheus + Loki data sources
│
├── docs/
│   ├── QUICK_START.md
│   ├── MVP_COMPLETE.md
│   └── ECommerce_Platform.postman_collection.json
│
├── scripts/
│   ├── test_e2e.ps1
│   ├── test_mvp_e2e.ps1
│   └── validate_mvp.ps1
│
├── logs/                           # Runtime logs (gitignored except .gitkeep)
│   └── .gitkeep
│
└── .github/
    └── workflows/
        └── ci.yml                  # GitHub Actions: pytest on push/PR to main
```

---

## 🔌 API Reference

All requests go through the API Gateway at `http://localhost:9000`.  
Auth-required endpoints need header: `Authorization: Bearer <token>`

### Health Checks
```
GET  /health                        → Gateway status
GET  /users/health                  → User Service
GET  /products/health               → Product Service
GET  /cart/health                   → Cart Service
GET  /orders/health                 → Order Service
GET  /payments/health               → Payment Service
GET  /notifications/health          → Notification Service
```

### User Service
```
POST /users/auth/register           → Register new user
POST /users/auth/login              → Login, returns JWT access_token
```

### Product Service
```
GET  /products                      → List all products
GET  /products/{id}                 → Get product by ID
POST /products                      → Create product
PUT  /products/{id}/deduct-stock    → Deduct inventory (called by Order Service)
```

### Shopping Cart  *(auth required)*
```
GET    /cart                        → View current user's cart
POST   /cart/items                  → Add item { product_id, quantity }
PUT    /cart/items/{product_id}     → Update quantity
DELETE /cart/items/{product_id}     → Remove item
```

### Order Service  *(auth required)*
```
POST   /orders                      → Create order { items: [{product_id, quantity}] }
GET    /orders                      → List current user's orders
GET    /orders/{id}                 → Order detail
PATCH  /orders/{id}/cancel          → Cancel order
```

### Payment Service
```
POST   /payments/checkout           → Process payment { order_id, amount, payment_method }
GET    /payments/{transaction_id}   → Get by transaction ID
GET    /payments/order/{order_id}   → Get by order ID
```

### Notification Service
```
POST   /notifications               → Create notification { user_id, message, event_type }
GET    /notifications/{id}          → Get notification by ID
```

### Metrics (Prometheus)
```
GET  /metrics                       → Available on each service's direct port (8000-8005, 9000)
```

---

## 🧪 Testing

Tests run **independently** of Docker — they use SQLite in-memory and mock all external calls.

```bash
# Setup
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run all 77 tests
pytest tests/ -v

# Run specific module
pytest tests/test_order_service.py -v

# Run with short traceback
pytest tests/ --tb=short
```

### CI/CD

Every push and PR to `main` automatically triggers the full test suite on GitHub Actions.  
See: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

---

## 📊 Monitoring & Logging

### Grafana Dashboards (`http://localhost:3000`)
- **Data Source: Prometheus** — total request count, request rate per service
- **Data Source: Loki** — centralized logs from all 7 services

### Prometheus (`http://localhost:9090`)
- Query: `http_requests_total` — total requests per service
- Query: `rate(http_requests_total[1m])` — real-time request rate

### Log Files
Each service writes rotating logs to `./logs/<service-name>.log`.  
Promtail tails these files and ships them to Loki for querying in Grafana Explore.

---

## 🔎 Troubleshooting

### Services not responding
```bash
docker compose ps            # Check all containers are Up
docker compose logs api-gateway --tail=50
docker compose restart <service-name>
```

### Consul not showing services
```bash
# Check Consul UI at http://localhost:8500
# All 7 services should be registered with green health checks
docker compose logs consul
```

### PostgreSQL connection errors
```bash
docker compose logs postgres
# Verify databases were created:
docker exec ecom-postgres psql -U postgres -c "\l"
```

### Kubernetes — pods stuck in ImagePullBackOff
```bash
# Build images locally first (required before kubectl apply)
docker build -t Bui-Tien-Dat-2808/user-service:latest -f Dockerfile .
# ... repeat for each service (see k8s/ README)
kubectl rollout restart deployment/<service-name>
```

### Kubernetes — NodePort :30000 ECONNREFUSED on Windows
Use port-forward instead:
```bash
kubectl port-forward service/api-gateway-service 9000:9000
```
Set Postman `base_url = http://localhost:9000` and test normally.

---

## ✅ Feature Checklist

- [x] 7 microservices with FastAPI
- [x] API Gateway with dynamic Consul-based routing
- [x] PostgreSQL — database-per-service pattern (6 databases)
- [x] Data persistence across container restarts
- [x] Consul service discovery + health checks
- [x] JWT authentication
- [x] Prometheus metrics (`/metrics` on all services)
- [x] Centralized logging (Loki + Promtail + Grafana)
- [x] 77 automated tests (unit + integration)
- [x] GitHub Actions CI/CD pipeline
- [x] Kubernetes manifests (Deployments, Services, PVC, ConfigMap, Secrets)
- [x] Postman collection for full E2E testing

---