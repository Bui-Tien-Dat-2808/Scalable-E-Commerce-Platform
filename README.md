# Scalable E-Commerce Platform

This project is a microservices-based e-commerce platform using FastAPI and Docker, featuring a complete MVP with user registration, product catalog, shopping cart, and order management.

## 🏗️ Architecture

### Services (7 total)
- **User Service** (port 8000): User registration, authentication, login
- **Product Catalog Service** (port 8001): Product listing, creation, inventory management
- **Cart Service** (port 8002): Shopping cart management per user
- **Order Service** (port 8003): Order creation and tracking
- **Payment Service** (port 8004): Payment processing stub
- **Notification Service** (port 8005): Email/SMS notification stub
- **API Gateway** (port 9000): Single entry point for all services with smart routing

### Stack
- **Framework**: FastAPI 0.111.0
- **Runtime**: Python 3.11-slim, Uvicorn 0.30.0
- **Validation**: Pydantic 2.13.4
- **Storage**: In-memory (MVP) / Ready for PostgreSQL migration
- **Orchestration**: Docker & Docker Compose
- **Testing**: Pytest 8.3.2

## 🚀 Quick Start

### Option 1: Docker (Recommended)
```bash
docker compose up --build
```

All services will start automatically on localhost:
- User Service: http://localhost:8000
- Product Service: http://localhost:8001
- Cart Service: http://localhost:8002
- Order Service: http://localhost:8003
- Payment Service: http://localhost:8004
- Notification Service: http://localhost:8005
- **API Gateway: http://localhost:9000** (primary entry point)

### Option 2: Local Development
```bash
# Setup
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run tests
pytest

# Start individual services in separate terminals
uvicorn services.user_service.app.main:app --reload
uvicorn services.product_service.app.main:app --host 0.0.0.0 --port 8001 --reload
uvicorn services.cart_service.app.main:app --host 0.0.0.0 --port 8002 --reload
uvicorn services.order_service.app.main:app --host 0.0.0.0 --port 8003 --reload
uvicorn services.payment_service.app.main:app --host 0.0.0.0 --port 8004 --reload
uvicorn services.notification_service.app.main:app --host 0.0.0.0 --port 8005 --reload
uvicorn api_gateway:app --host 0.0.0.0 --port 9000 --reload
```

## 📋 MVP Features

### User Management
- **POST** `/users/auth/register` - Register new user
  ```powershell
  $body = @{username="alice"; email="alice@example.com"; password="pass123"} | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "http://localhost:9000/users/auth/register" `
    -ContentType 'application/json' -Body $body
  ```
  Response: `{"username":"alice","email":"alice@example.com"}`

- **POST** `/users/auth/login` - Login user
  ```powershell
  $body = @{email="alice@example.com"; password="pass123"} | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "http://localhost:9000/users/auth/login" `
    -ContentType 'application/json' -Body $body
  ```
  Response: `{"access_token":"<jwt>","token_type":"bearer","user":{"id":1,"username":"alice","email":"alice@example.com"}}`

### Product Catalog
- **GET** `/products` - List all products (seeded with Laptop, Smartphone)
  ```powershell
  Invoke-RestMethod -Method Get -Uri "http://localhost:9000/products"
  ```
  Response: `{"products":[{"id":1,"name":"Laptop","price":999.99,"stock":10},...]}` 

- **POST** `/products` - Create new product
  ```powershell
  $body = @{name="Monitor"; price=299.99; stock=15} | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "http://localhost:9000/products" `
    -ContentType 'application/json' -Body $body
  ```

### Shopping Cart
- **GET** `/cart` - View current user's cart
  ```powershell
  Invoke-RestMethod -Method Get -Uri "http://localhost:9000/cart" `
    -Headers @{Authorization="Bearer $token"}
  ```

- **POST** `/cart/items` - Add item to cart
  ```powershell
  $body = @{product_id=1; quantity=2} | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri "http://localhost:9000/cart/items" `
    -Headers @{Authorization="Bearer $token"} `
    -ContentType 'application/json' -Body $body
  ```

- **PUT** `/cart/items/{product_id}` - Update quantity
  ```powershell
  $body = @{quantity=3} | ConvertTo-Json
  Invoke-RestMethod -Method Put -Uri "http://localhost:9000/cart/items/1" `
    -Headers @{Authorization="Bearer $token"} `
    -ContentType 'application/json' -Body $body
  ```

- **DELETE** `/cart/items/{product_id}` - Remove item
  ```powershell
  Invoke-RestMethod -Method Delete -Uri "http://localhost:9000/cart/items/1" `
    -Headers @{Authorization="Bearer $token"}
  ```

### Order Management
- **POST** `/orders` - Create order
  ```powershell
  $body = @{items=@(@{product_id=1;quantity=1})} | ConvertTo-Json -Depth 10
  Invoke-RestMethod -Method Post -Uri "http://localhost:9000/orders" `
    -Headers @{Authorization="Bearer $token"} `
    -ContentType 'application/json' -Body $body
  ```
  Response: `{"id":1,"order_id":"ORD-1","user_id":"1","items":[...],"status":"created"}`

- **GET** `/orders` - List current user's orders
- **GET** `/orders/{id}` - View order details
- **PATCH** `/orders/{id}/cancel` - Cancel an order

## 🧪 Run Full End-to-End Test

```powershell
# PowerShell script to test complete flow
$ts = Get-Date -Format "HHmmss"
$email = "user$ts@example.com"

# 1. Register
$reg = @{username="user$ts"; email=$email; password="Pass123!"} | ConvertTo-Json
$user = Invoke-RestMethod -Method Post -Uri "http://localhost:9000/users/auth/register" `
  -ContentType 'application/json' -Body $reg
Write-Host "✓ Registered: $($user.username)"

# 2. Login
$login = @{email=$email; password="Pass123!"} | ConvertTo-Json
$auth = Invoke-RestMethod -Method Post -Uri "http://localhost:9000/users/auth/login" `
  -ContentType 'application/json' -Body $login
Write-Host "✓ Logged in with token: $($auth.access_token.Substring(0,15))..."

# 3. Get products
$products = Invoke-RestMethod -Method Get -Uri "http://localhost:9000/products"
Write-Host "✓ Found $($products.products.Count) products"

# 4. Add to cart
$cart = @{product_id=1; quantity=2} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:9000/cart/items" `
  -Headers @{Authorization="Bearer $($auth.access_token)"} `
  -ContentType 'application/json' -Body $cart
Write-Host "✓ Added item to cart"

# 5. Create order
$order = @{items=@(@{product_id=1;quantity=1})} | ConvertTo-Json -Depth 10
$result = Invoke-RestMethod -Method Post -Uri "http://localhost:9000/orders" `
  -Headers @{Authorization="Bearer $($auth.access_token)"} `
  -ContentType 'application/json' -Body $order
Write-Host "✓ Order $($result.order_id) created successfully"
```

## 📁 Project Structure
```
.
├── services/
│   ├── user_service/
│   │   └── app/main.py           # Registration, login endpoints
│   ├── product_service/
│   │   └── app/main.py           # Products CRUD with seeded data
│   ├── cart_service/
│   │   └── app/main.py           # Shopping cart per user
│   ├── order_service/
│   │   └── app/main.py           # Order creation/tracking
│   ├── payment_service/
│   │   └── app/main.py           # Payment processing stub
│   └── notification_service/
│       └── app/main.py           # Email notification stub
├── api_gateway.py                # API Gateway with smart routing
├── docker-compose.yml            # 7-service orchestration
├── Dockerfile                    # Multi-service Docker image
├── requirements.txt              # Python dependencies
├── README.md                     # This file
└── tests/
    ├── test_user_service.py      # User service tests
    ├── test_mvp_flow.py          # Integration flow tests
    └── test_gateway.py           # Gateway routing tests
```

## 🔌 API Gateway Routing

The API Gateway automatically routes requests to the correct service based on the first path segment:

```
/users/*          → User Service (8000)
/products/*       → Product Service (8001)
/cart/*           → Cart Service (8002)
/orders/*         → Order Service (8003)
/payments/*       → Payment Service (8004)
/notifications/*  → Notification Service (8005)
```

**Important**: All routes must include the service prefix when calling through the gateway.

### Gateway Examples
```powershell
# Gateway routes (use service prefix)
POST   /users/auth/register          → User Service
POST   /users/auth/login             → User Service
GET    /products                     → Product Service
POST   /products                     → Product Service
GET    /cart                         → Cart Service
POST   /cart/items                   → Cart Service
PUT    /cart/items/{product_id}      → Cart Service
DELETE /cart/items/{product_id}      → Cart Service
POST   /orders                       → Order Service
GET    /orders                       → Order Service
GET    /orders/{id}                  → Order Service
PATCH  /orders/{id}/cancel           → Order Service

# Direct service access (optional, without gateway)
POST   http://localhost:8000/auth/register     # Direct to user-service
GET    http://localhost:8001/products          # Direct to product-service
```

## 📊 Seeded Data

The MVP includes pre-populated product catalog:
- **Laptop**: $999.99 (10 in stock)
- **Smartphone**: $499.99 (20 in stock)

## 🔄 In-Memory Storage

Currently, all services use in-memory storage (Python dicts/lists):
- User data resets on service restart
- Products initialize with seed data
- Carts reset on restart
- Orders reset on restart

Perfect for MVP testing. **Next Phase**: PostgreSQL integration for persistence.

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_user_service.py

# Run with coverage
pytest --cov=services --cov=api_gateway
```

### Test Files
- `tests/test_user_service.py` - User service unit tests
- `tests/test_mvp_flow.py` - End-to-end integration tests
- `tests/test_gateway.py` - API Gateway routing tests

## 📝 Status

✅ **MVP Complete**
- [x] User Service (register, login)
- [x] Product Catalog (listing, creation, seeded data)
- [x] Shopping Cart (user-specific carts)
- [x] Order Management (order creation)
- [x] API Gateway (full request routing)
- [x] Docker setup (all 7 services)
- [x] Test suite

📋 **Next Phases**
- [ ] Payment Service (mock Stripe integration)
- [ ] Notification Service (email queue)
- [ ] Inter-service communication (inventory checks, order callbacks)
- [ ] PostgreSQL database integration
- [ ] JWT token authentication
- [ ] Error handling & validation improvements
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Load balancing & scaling configuration

## 🐛 Troubleshooting

### Services not accessible
```bash
# Check all services are running
docker compose ps

# Check gateway logs
docker compose logs api-gateway

# Restart services
docker compose restart
```

### Port conflicts
Modify ports in `docker-compose.yml` if default ports are in use.

### Database persistence
To add PostgreSQL, see the "Next Phases" section above.

## 📄 License
MIT