import json
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx

app = FastAPI(title="API Gateway", version="1.0.0")

SERVICE_URLS = {
    "users": os.getenv("USER_SERVICE_URL", "http://user-service:8000"),
    "products": os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8001"),
    "cart": os.getenv("CART_SERVICE_URL", "http://cart-service:8002"),
    "carts": os.getenv("CART_SERVICE_URL", "http://cart-service:8002"),
    "orders": os.getenv("ORDER_SERVICE_URL", "http://order-service:8003"),
    "payments": os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8004"),
    "notifications": os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8005"),
}


def build_target_path(service: str, path: str) -> str:
    # ── Global: health check luôn route về /health ────────────────────────
    if path == "health":
        return "/health"

    # ── Empty path: route về resource gốc của từng service ───────────────
    if not path:
        if service == "users":
            return "/"
        if service == "products":
            return "/products"
        if service in {"cart", "carts"}:
            return "/cart"
        if service == "orders":
            return "/orders"
        if service == "payments":
            return "/payments"
        if service == "notifications":
            return "/notifications"
        return "/"

    # ── Có path: routing theo từng service ───────────────────────────────
    if service == "users":
        return f"/{path}"
    if service == "products":
        if path.startswith("products"):
            return f"/{path}"
        return f"/products/{path}"
    if service in {"cart", "carts"}:
        if path.startswith("cart"):
            return f"/{path}"
        if path.startswith("carts"):
            return "/cart" + path.removeprefix("carts")
        return f"/cart/{path}"
    if service == "orders":
        if path.startswith("orders"):
            return f"/{path}"
        return f"/orders/{path}"
    if service == "payments":
        if path.startswith("payments"):
            return f"/{path}"
        return f"/payments/{path}"
    if service == "notifications":
        if path.startswith("notifications"):
            return f"/{path}"
        return f"/notifications/{path}"
    return f"/{path}"


@app.get("/")
def root():
    return {"service": "api-gateway", "message": "API gateway is running"}


@app.get("/health")
def health_check():
    return {"service": "api-gateway", "status": "ok"}


@app.api_route("/{service}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_root(service: str, request: Request):
    return await proxy(service, "", request)


@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy(service: str, path: str, request: Request):
    if service not in SERVICE_URLS:
        raise HTTPException(status_code=404, detail="Service not found")

    target_path = build_target_path(service, path)
    body = await request.body()
    headers = {key: value for key, value in request.headers.items() if key.lower() not in {"host", "content-length"}}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(
            method=request.method,
            url=f"{SERVICE_URLS[service]}{target_path}",
            params=request.query_params,
            content=body,
            headers=headers,
        )

    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        payload = {"message": response.text}

    return JSONResponse(status_code=response.status_code, content=payload)
