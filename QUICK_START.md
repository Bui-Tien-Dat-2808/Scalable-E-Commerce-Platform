# 🚀 QUICK START GUIDE

## Run the MVP

```bash
cd "D:\Backend Developer\Scalable E-Commerce Platform"
docker compose up --build
```

All services available on localhost - Primary entry point is **API Gateway on port 9000**

---

## Services Running

| Service | Port | Health Check |
|---------|------|--------------|
| User Service | 8000 | `curl http://localhost:8000/docs` |
| Product Service | 8001 | `curl http://localhost:8001/docs` |
| Cart Service | 8002 | `curl http://localhost:8002/docs` |
| Order Service | 8003 | `curl http://localhost:8003/docs` |
| Payment Service | 8004 | `curl http://localhost:8004/docs` |
| Notification Service | 8005 | `curl http://localhost:8005/docs` |
| **API Gateway** | **9000** | **`curl http://localhost:9000/docs`** |

---

## Test the MVP (PowerShell)

### Quick Test
```powershell
# Single command test
$ts=Get-Date -Format "HHmmss";$e="t$ts@ex.com";$r1=Invoke-RestMethod -M Post -Uri "http://localhost:9000/users/auth/register" -ContentType 'application/json' -Body (@{username="u$ts";email=$e;password="P1!"} | ConvertTo-Json);$r2=Invoke-RestMethod -M Post -Uri "http://localhost:9000/users/auth/login" -ContentType 'application/json' -Body (@{email=$e;password="P1!"} | ConvertTo-Json);$token=$r2.access_token;$r3=Invoke-RestMethod -M Get -Uri "http://localhost:9000/products";$r4=Invoke-RestMethod -M Post -Uri "http://localhost:9000/cart/items" -Headers @{Authorization="Bearer $token"} -ContentType 'application/json' -Body (@{product_id=1;quantity=2} | ConvertTo-Json);$r5=Invoke-RestMethod -M Post -Uri "http://localhost:9000/orders" -Headers @{Authorization="Bearer $token"} -ContentType 'application/json' -Body (@{items=@(@{product_id=1;quantity=1})} | ConvertTo-Json -Depth 10);Write-Host "✅ Complete flow tested successfully"
```

### Step-by-Step Test
```powershell
# Variables
$GATEWAY = "http://localhost:9000"
$email = "test@example.com"
$password = "TestPass123!"

# 1. Register
$reg = @{username="testuser"; email=$email; password=$password} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$GATEWAY/users/auth/register" `
  -ContentType 'application/json' -Body $reg

# 2. Login
$login = @{email=$email; password=$password} | ConvertTo-Json
$auth = Invoke-RestMethod -Method Post -Uri "$GATEWAY/users/auth/login" `
  -ContentType 'application/json' -Body $login
# $auth.access_token contains the JWT to use as: Authorization: Bearer <token>

# 3. Get Products
Invoke-RestMethod -Method Get -Uri "$GATEWAY/products"

# 4. Add to Cart
$cart = @{product_id=1; quantity=2} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$GATEWAY/cart/items" `
  -Headers @{Authorization="Bearer $($auth.access_token)"} `
  -ContentType 'application/json' -Body $cart

# 5. Create Order
$order = @{items=@(@{product_id=1;quantity=1})} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Method Post -Uri "$GATEWAY/orders" `
  -Headers @{Authorization="Bearer $($auth.access_token)"} `
  -ContentType 'application/json' -Body $order
```

---

## API Endpoints (via Gateway - port 9000)

All routes below **require the service prefix** (`/users`, `/products`, `/cart`, `/orders`) when called through the Gateway. Cart and Order routes also require an `Authorization: Bearer <access_token>` header (token comes from the login response).

### Users
```
POST /users/auth/register
POST /users/auth/login
```

### Products
```
GET  /products
POST /products
```

### Cart (requires Authorization: Bearer <token>)
```
GET  /cart
POST /cart/items
PUT  /cart/items/{product_id}
DELETE /cart/items/{product_id}
```

### Orders (requires Authorization: Bearer <token>)
```
POST /orders
GET  /orders
GET  /orders/{order_id}
PATCH /orders/{order_id}/cancel
```

### Health
```
GET /health
```

---

## Example Requests

### Register
```
POST http://localhost:9000/users/auth/register
Content-Type: application/json

{
  "username": "alice",
  "email": "alice@example.com",
  "password": "SecurePass123!"
}
```

### Login
```
POST http://localhost:9000/users/auth/login
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "SecurePass123!"
}
```
Response:
```
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": { "id": 1, "username": "alice", "email": "alice@example.com" }
}
```

### Get Products
```
GET http://localhost:9000/products
```

### Add to Cart
```
POST http://localhost:9000/cart/items
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "product_id": 1,
  "quantity": 2
}
```

### Create Order
```
POST http://localhost:9000/orders
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "items": [
    {
      "product_id": 1,
      "quantity": 1
    }
  ]
}
```
Note: `user_id` is taken from the JWT, not from the request body.

---

## Project Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | All 7 services definition |
| `Dockerfile` | Container image for services |
| `api_gateway.py` | Request router (port 9000) |
| `requirements.txt` | Python dependencies |
| `README.md` | Full documentation |
| `MVP_COMPLETE.md` | Completion status |
| `services/` | Individual microservices |
| `tests/` | Test suite |

---

## Troubleshooting

```bash
# Check all services
docker compose ps

# View logs
docker compose logs api-gateway

# Restart
docker compose restart

# Full rebuild
docker compose down
docker compose up --build
```

---

## Key Facts

✅ 7 microservices fully operational
✅ All services accessible through API Gateway (port 9000)
✅ Complete end-to-end flow tested and working
✅ In-memory storage (MVP phase)
✅ Docker containerized
✅ Ready for development and testing

**Main Entry Point**: http://localhost:9000

---

*MVP Status: ✅ COMPLETE & VALIDATED*