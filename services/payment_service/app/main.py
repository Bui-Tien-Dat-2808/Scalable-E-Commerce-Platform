import os
from uuid import uuid4
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db
from services.common.consul import consul_client

from prometheus_fastapi_instrumentator import Instrumentator
from services.common.logging import setup_logger

SERVICE_NAME = os.getenv("SERVICE_NAME", "payment-service")
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8004"))
INSTANCE_ID = f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'default')}"

logger = setup_logger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up payment-service...")
    # Startup: Đăng ký với Consul
    consul_client.register_service(SERVICE_NAME, INSTANCE_ID, SERVICE_HOST, SERVICE_PORT)
    yield
    logger.info("Shutting down payment-service...")
    # Shutdown: Huỷ đăng ký khỏi Consul
    consul_client.deregister_service(INSTANCE_ID)


app = FastAPI(title="Payment Service", version="1.0.0", lifespan=lifespan)
# Expose /metrics
Instrumentator().instrument(app).expose(app)


# ── Model ─────────────────────────────────────────────────────────────────────

class PaymentModel(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(50), unique=True, index=True, nullable=False)
    order_id = Column(String(50), index=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    payment_method = Column(String(50), default="card")
    status = Column(String(20), nullable=False)  # approved | failed


Base.metadata.create_all(bind=engine)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PaymentCreateRequest(BaseModel):
    order_id: str = Field(..., min_length=1, description="Order ID must not be empty")
    amount: float = Field(0.0, ge=0.0, description="Amount must be non-negative")
    currency: str = Field("USD", min_length=3, max_length=3, description="Currency must be a 3-letter code")
    payment_method: str = Field("card", min_length=1, description="Payment method must not be empty")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "payment-service", "message": "Payment service is running"}


@app.get("/health")
def health_check():
    return {"service": "payment-service", "status": "ok"}


@app.post("/payments/checkout")
def create_payment_session(payload: PaymentCreateRequest, db: Session = Depends(get_db)):
    transaction_id = f"TXN-{uuid4().hex[:12].upper()}"
    status = (
        "approved"
        if payload.amount > 0 and payload.payment_method.lower() not in {"fail", "declined"}
        else "failed"
    )
    payment = PaymentModel(
        transaction_id=transaction_id,
        order_id=payload.order_id,
        amount=payload.amount,
        currency=payload.currency,
        payment_method=payload.payment_method,
        status=status,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return _to_dict(payment)


@app.get("/payments/{transaction_id}")
def get_payment_status(transaction_id: str, db: Session = Depends(get_db)):
    payment = db.query(PaymentModel).filter(PaymentModel.transaction_id == transaction_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _to_dict(payment)


@app.get("/payments/by-order/{order_id}")
def get_payment_by_order(order_id: str, db: Session = Depends(get_db)):
    """Tra cứu payment theo order_id."""
    payment = db.query(PaymentModel).filter(PaymentModel.order_id == order_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found for this order")
    return _to_dict(payment)


def _to_dict(p: PaymentModel) -> dict:
    return {
        "transaction_id": p.transaction_id,
        "order_id": p.order_id,
        "amount": p.amount,
        "currency": p.currency,
        "payment_method": p.payment_method,
        "status": p.status,
    }