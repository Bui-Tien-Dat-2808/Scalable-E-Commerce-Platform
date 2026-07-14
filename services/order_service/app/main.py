import logging
import os

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from services.common.security import get_current_user_id

logger = logging.getLogger("order_service")

app = FastAPI(title="Order Service", version="1.0.0")

# URLs của các service phụ thuộc (override bằng env vars trong Docker)
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8001")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8004")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8005")

# Các trạng thái hợp lệ của order
ORDER_STATUSES = ("created", "pending_payment", "paid", "failed_payment", "cancelled", "shipped", "delivered")


class OrderItem(BaseModel):
    product_id: int
    quantity: int


class OrderCreateRequest(BaseModel):
    items: list[OrderItem]
    payment_method: str = "card"
    currency: str = "USD"
    # Email người nhận notification (tuỳ chọn, fallback về user_id)
    recipient_email: str | None = None


orders_db: list[dict] = []


def find_order(order_id: int) -> dict | None:
    return next((order for order in orders_db if order["id"] == order_id), None)


def _fetch_product(product_id: int) -> dict:
    """Gọi Product Service để lấy thông tin sản phẩm."""
    try:
        resp = httpx.get(f"{PRODUCT_SERVICE_URL}/products/{product_id}", timeout=5.0)
        if resp.status_code == 404:
            raise HTTPException(status_code=400, detail=f"Product {product_id} not found")
        resp.raise_for_status()
        return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not reach product-service: %s", exc)
        raise HTTPException(status_code=503, detail="Product service unavailable")


def _deduct_stock(product_id: int, quantity: int) -> None:
    """Trừ tồn kho trên Product Service. Raise 400 nếu không đủ hàng."""
    try:
        resp = httpx.patch(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}/deduct-stock",
            json={"quantity": quantity},
            timeout=5.0,
        )
        if resp.status_code == 409:
            raise HTTPException(status_code=400, detail=resp.json().get("detail", "Insufficient stock"))
        if resp.status_code == 404:
            raise HTTPException(status_code=400, detail=f"Product {product_id} not found")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not reach product-service for stock deduction: %s", exc)
        raise HTTPException(status_code=503, detail="Product service unavailable")


def _process_payment(order_id: str, amount: float, currency: str, payment_method: str) -> dict:
    """Gọi Payment Service để xử lý thanh toán."""
    try:
        resp = httpx.post(
            f"{PAYMENT_SERVICE_URL}/payments/checkout",
            json={
                "order_id": order_id,
                "amount": amount,
                "currency": currency,
                "payment_method": payment_method,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Payment service error: %s", exc)
        # Trả về failed nếu không liên lạc được
        return {"status": "failed", "transaction_id": None, "error": str(exc)}


def _send_notification(recipient: str, event_type: str, message: str, subject: str) -> None:
    """Gửi notification — fire-and-forget, lỗi không ảnh hưởng response."""
    try:
        httpx.post(
            f"{NOTIFICATION_SERVICE_URL}/notifications",
            json={
                "channel": "email",
                "recipient": recipient,
                "subject": subject,
                "message": message,
                "event_type": event_type,
            },
            timeout=5.0,
        )
    except Exception as exc:
        logger.warning("Notification service error (non-critical): %s", exc)


@app.get("/")
def root():
    return {"service": "order-service", "message": "Order service is running"}


@app.get("/health")
def health_check():
    return {"service": "order-service", "status": "ok"}


@app.post("/orders", status_code=201)
def create_order(payload: OrderCreateRequest, user_id: str = Depends(get_current_user_id)):
    """
    Orchestrator chính:
    1. Lấy thông tin & trừ tồn kho từng sản phẩm
    2. Tạo order với status = pending_payment
    3. Gọi Payment Service
    4. Cập nhật status → paid / failed_payment
    5. Gửi Notification (fire-and-forget)
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    # ── Bước 1: Lấy giá sản phẩm & kiểm tra tồn kho ──
    order_items_detail = []
    total_amount = 0.0
    deducted: list[tuple[int, int]] = []  # track để rollback nếu cần

    for item in payload.items:
        product = _fetch_product(item.product_id)
        # Thử trừ tồn kho — nếu thất bại thì rollback những item đã trừ
        try:
            _deduct_stock(item.product_id, item.quantity)
        except HTTPException as exc:
            # Rollback: cộng lại stock đã trừ trước đó (best-effort)
            for prev_id, prev_qty in deducted:
                try:
                    httpx.patch(
                        f"{PRODUCT_SERVICE_URL}/products/{prev_id}/deduct-stock",
                        json={"quantity": -prev_qty},  # âm = cộng lại (nếu service hỗ trợ)
                        timeout=3.0,
                    )
                except Exception:
                    pass  # rollback best-effort
            raise exc

        deducted.append((item.product_id, item.quantity))
        item_total = product["price"] * item.quantity
        total_amount += item_total
        order_items_detail.append({
            "product_id": item.product_id,
            "name": product["name"],
            "price": product["price"],
            "quantity": item.quantity,
            "subtotal": item_total,
        })

    # ── Bước 2: Tạo order ──
    order_id = len(orders_db) + 1
    order_ref = f"ORD-{order_id}"
    order = {
        "id": order_id,
        "order_id": order_ref,
        "user_id": user_id,
        "items": order_items_detail,
        "total_amount": round(total_amount, 2),
        "currency": payload.currency,
        "status": "pending_payment",
        "transaction_id": None,
        "payment_status": None,
    }
    orders_db.append(order)

    # ── Bước 3: Xử lý thanh toán ──
    payment_result = _process_payment(
        order_id=order_ref,
        amount=total_amount,
        currency=payload.currency,
        payment_method=payload.payment_method,
    )
    payment_approved = payment_result.get("status") == "approved"

    # ── Bước 4: Cập nhật order status ──
    order["transaction_id"] = payment_result.get("transaction_id")
    order["payment_status"] = payment_result.get("status")
    order["status"] = "paid" if payment_approved else "failed_payment"

    # ── Bước 5: Gửi notification (fire-and-forget) ──
    recipient = payload.recipient_email or f"user_{user_id}@example.com"
    if payment_approved:
        _send_notification(
            recipient=recipient,
            event_type="order_paid",
            subject=f"Order {order_ref} Confirmed ✓",
            message=f"Your order {order_ref} has been placed and payment of {payload.currency} {total_amount:.2f} was successful.",
        )
    else:
        _send_notification(
            recipient=recipient,
            event_type="order_failed",
            subject=f"Order {order_ref} Payment Failed",
            message=f"Your order {order_ref} could not be completed due to a payment failure. Please try again.",
        )

    return order


@app.get("/orders")
def list_orders(user_id: str = Depends(get_current_user_id)):
    return {"orders": [order for order in orders_db if order["user_id"] == user_id]}


@app.get("/orders/{order_id}")
def get_order(order_id: int, user_id: str = Depends(get_current_user_id)):
    order = find_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return order


@app.patch("/orders/{order_id}/cancel")
def cancel_order(order_id: int, user_id: str = Depends(get_current_user_id)):
    order = find_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if order["status"] in ("cancelled", "shipped", "delivered"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel order with status '{order['status']}'")

    order["status"] = "cancelled"
    # Gửi notification huỷ đơn
    _send_notification(
        recipient=f"user_{user_id}@example.com",
        event_type="order_cancelled",
        subject=f"Order {order['order_id']} Cancelled",
        message=f"Your order {order['order_id']} has been cancelled.",
    )
    return order
