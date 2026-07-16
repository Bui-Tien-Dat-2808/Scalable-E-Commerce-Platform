import os
from contextlib import asynccontextmanager
from typing import Optional
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db
from services.common.security import get_current_user_id
from services.common.consul import consul_client

from prometheus_fastapi_instrumentator import Instrumentator
from services.common.logging import setup_logger
from services.common.error_handler import setup_error_handlers

SERVICE_NAME = os.getenv("SERVICE_NAME", "order-service")
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8003"))
INSTANCE_ID = f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'default')}"

logger = setup_logger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up order-service...")
    # Startup: Register with Consul
    consul_client.register_service(SERVICE_NAME, INSTANCE_ID, SERVICE_HOST, SERVICE_PORT)
    yield
    logger.info("Shutting down order-service...")
    # Shutdown: Deregister from Consul
    consul_client.deregister_service(INSTANCE_ID)


app = FastAPI(title="Order Service", version="1.0.0", lifespan=lifespan)
# Expose /metrics
Instrumentator().instrument(app).expose(app)
setup_error_handlers(app)


# ── Models ────────────────────────────────────────────────────────────────────

class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_ref = Column(String(20), unique=True, index=True, nullable=False)
    user_id = Column(String(50), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="pending_payment")
    total_amount = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), default="USD")
    transaction_id = Column(String(50), nullable=True)
    payment_status = Column(String(20), nullable=True)


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(255), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    subtotal = Column(Float, nullable=False)


Base.metadata.create_all(bind=engine)


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrderItem(BaseModel):
    product_id: int = Field(..., gt=0, description="Product ID must be greater than zero")
    quantity: int = Field(..., gt=0, description="Quantity must be greater than zero")


class OrderCreateRequest(BaseModel):
    items: list[OrderItem] = Field(..., min_length=1, description="Order must contain at least one item")
    payment_method: str = Field("card", min_length=1)
    currency: str = Field("USD", min_length=3, max_length=3)
    recipient_email: str | None = None


class OrderItemResponse(BaseModel):
    product_id: int
    name: str
    price: float
    quantity: int
    subtotal: float


class OrderResponse(BaseModel):
    id: int
    order_id: str
    user_id: str
    status: str
    total_amount: float
    currency: str
    transaction_id: Optional[str] = None
    payment_status: Optional[str] = None
    items: list[OrderItemResponse]


class PaginatedOrderResponse(BaseModel):
    data: list[OrderResponse]
    total: int
    page: int
    limit: int
    pages: int


# ── Inter-service HTTP helpers ────────────────────────────────────────────────

def _fetch_product(product_id: int) -> dict:
    try:
        product_service_url = consul_client.resolve_service("product-service")
        resp = httpx.get(f"{product_service_url}/products/{product_id}", timeout=5.0)
        if resp.status_code == 404:
            raise HTTPException(status_code=400, detail=f"Product {product_id} not found")
        resp.raise_for_status()
        return resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Product service unreachable: %s", exc)
        raise HTTPException(status_code=503, detail="Product service unavailable")


def _deduct_stock(product_id: int, quantity: int) -> None:
    try:
        product_service_url = consul_client.resolve_service("product-service")
        resp = httpx.patch(
            f"{product_service_url}/products/{product_id}/deduct-stock",
            json={"quantity": quantity},
            timeout=5.0,
        )
        if resp.status_code == 409:
            err_data = resp.json()
            err_msg = err_data.get("error", {}).get("message") or err_data.get("detail", "Insufficient stock")
            raise HTTPException(status_code=400, detail=err_msg)
        if resp.status_code == 404:
            raise HTTPException(status_code=400, detail=f"Product {product_id} not found")
        resp.raise_for_status()
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Stock deduction failed: %s", exc)
        raise HTTPException(status_code=503, detail="Product service unavailable")


def _process_payment(order_id: str, amount: float, currency: str, payment_method: str) -> dict:
    try:
        payment_service_url = consul_client.resolve_service("payment-service")
        resp = httpx.post(
            f"{payment_service_url}/payments/checkout",
            json={"order_id": order_id, "amount": amount, "currency": currency, "payment_method": payment_method},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Payment service error: %s", exc)
        return {"status": "failed", "transaction_id": None}


def _send_notification(recipient: str, event_type: str, message: str, subject: str) -> None:
    try:
        notification_service_url = consul_client.resolve_service("notification-service")
        httpx.post(
            f"{notification_service_url}/notifications",
            json={"channel": "email", "recipient": recipient, "subject": subject,
                  "message": message, "event_type": event_type},
            timeout=5.0,
        )
    except Exception as exc:
        logger.warning("Notification error (non-critical): %s", exc)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "order-service", "message": "Order service is running"}


@app.get("/health")
def health_check():
    return {"service": "order-service", "status": "ok"}


@app.post("/orders", status_code=201, response_model=OrderResponse, tags=["Orders"])
def create_order(
    payload: OrderCreateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Create a new order (Deduct stock -> Process payment -> Send notification)."""
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    # Step 1: Fetch price & deduct stock
    items_detail = []
    total_amount = 0.0
    deducted: list[tuple[int, int]] = []

    for item in payload.items:
        product = _fetch_product(item.product_id)
        try:
            _deduct_stock(item.product_id, item.quantity)
        except HTTPException as exc:
            # Rollback deducted stock (best-effort)
            for pid, qty in deducted:
                try:
                    product_service_url = consul_client.resolve_service("product-service")
                    httpx.patch(f"{product_service_url}/products/{pid}/deduct-stock",
                                json={"quantity": -qty}, timeout=3.0)
                except Exception:
                    pass
            raise exc

        deducted.append((item.product_id, item.quantity))
        item_total = round(product["price"] * item.quantity, 2)
        total_amount += item_total
        items_detail.append({
            "product_id": item.product_id,
            "name": product["name"],
            "price": product["price"],
            "quantity": item.quantity,
            "subtotal": item_total,
        })

    total_amount = round(total_amount, 2)

    # Step 2: Create order in DB
    order = OrderModel(
        order_ref="TEMP",  # will be updated after retrieving id
        user_id=user_id,
        status="pending_payment",
        total_amount=total_amount,
        currency=payload.currency,
    )
    db.add(order)
    db.flush()  # get id before commit

    order.order_ref = f"ORD-{order.id}"
    for detail in items_detail:
        db.add(OrderItemModel(
            order_id=order.id,
            product_id=detail["product_id"],
            product_name=detail["name"],
            price=detail["price"],
            quantity=detail["quantity"],
            subtotal=detail["subtotal"],
        ))
    db.commit()
    db.refresh(order)

    # Step 3: Payment
    payment_result = _process_payment(
        order_id=order.order_ref,
        amount=total_amount,
        currency=payload.currency,
        payment_method=payload.payment_method,
    )
    payment_approved = payment_result.get("status") == "approved"

    order.transaction_id = payment_result.get("transaction_id")
    order.payment_status = payment_result.get("status")
    order.status = "paid" if payment_approved else "failed_payment"
    db.commit()
    db.refresh(order)

    # Step 4: Notification (fire-and-forget)
    recipient = payload.recipient_email or f"user_{user_id}@example.com"
    if payment_approved:
        _send_notification(recipient, "order_paid",
                           f"Order {order.order_ref} confirmed! Total: {payload.currency} {total_amount}",
                           f"Order {order.order_ref} Confirmed ✓")
    else:
        _send_notification(recipient, "order_failed",
                           f"Order {order.order_ref} payment failed. Please try again.",
                           f"Order {order.order_ref} Payment Failed")

    return _order_to_response(order, [OrderItemResponse(**i) for i in items_detail])


@app.get("/orders", response_model=PaginatedOrderResponse, tags=["Orders"])
def list_orders(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starting from 1)"),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    status: Optional[str] = Query(None, description="Filter by order status"),
):
    """Get list of user's orders (with pagination and filtering)."""
    query = db.query(OrderModel).filter(OrderModel.user_id == user_id)
    if status:
        query = query.filter(OrderModel.status == status)
    total = query.count()
    pages = max(1, -(-total // limit))
    orders = query.offset((page - 1) * limit).limit(limit).all()
    
    data = []
    for o in orders:
        items = _get_items(o.id, db)
        data.append(_order_to_response(o, items))
        
    return PaginatedOrderResponse(
        data=data,
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@app.get("/orders/{order_id}", response_model=OrderResponse, tags=["Orders"])
def get_order(order_id: int, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Get details of a specific order (owner only)."""
    order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return _order_to_response(order, _get_items(order.id, db))


@app.patch("/orders/{order_id}/cancel", response_model=OrderResponse, tags=["Orders"])
def cancel_order(order_id: int, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Cancel a specific order (owner only)."""
    order = db.query(OrderModel).filter(OrderModel.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if order.status in ("cancelled", "shipped", "delivered"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel order with status '{order.status}'")

    order.status = "cancelled"
    db.commit()
    db.refresh(order)

    _send_notification(
        f"user_{user_id}@example.com", "order_cancelled",
        f"Order {order.order_ref} has been cancelled.",
        f"Order {order.order_ref} Cancelled",
    )
    return _order_to_response(order, _get_items(order.id, db))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_items(order_id: int, db: Session) -> list[OrderItemResponse]:
    items = db.query(OrderItemModel).filter(OrderItemModel.order_id == order_id).all()
    return [OrderItemResponse(
        product_id=i.product_id,
        name=i.product_name,
        price=i.price,
        quantity=i.quantity,
        subtotal=i.subtotal
    ) for i in items]


def _order_to_response(order: OrderModel, items: list[OrderItemResponse]) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        order_id=order.order_ref,
        user_id=order.user_id,
        status=order.status,
        total_amount=order.total_amount,
        currency=order.currency,
        transaction_id=order.transaction_id,
        payment_status=order.payment_status,
        items=items,
    )
