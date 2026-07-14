from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uuid import uuid4

app = FastAPI(title="Payment Service", version="1.0.0")


class PaymentCreateRequest(BaseModel):
    order_id: str
    amount: float = 0.0
    currency: str = "USD"
    payment_method: str = "card"


payments_db: dict[str, dict] = {}
# Index phụ: tra cứu payment theo order_id
payments_by_order: dict[str, str] = {}


@app.get("/")
def root():
    return {"service": "payment-service", "message": "Payment service is running"}


@app.get("/health")
def health_check():
    return {"service": "payment-service", "status": "ok"}


@app.post("/payments/checkout")
def create_payment_session(payload: PaymentCreateRequest):
    transaction_id = f"TXN-{uuid4().hex[:12].upper()}"
    status = (
        "approved"
        if payload.amount > 0 and payload.payment_method.lower() not in {"fail", "declined"}
        else "failed"
    )
    payment = {
        "transaction_id": transaction_id,
        "order_id": payload.order_id,
        "amount": payload.amount,
        "currency": payload.currency,
        "payment_method": payload.payment_method,
        "status": status,
    }
    payments_db[transaction_id] = payment
    payments_by_order[payload.order_id] = transaction_id
    return payment


@app.get("/payments/{transaction_id}")
def get_payment_status(transaction_id: str):
    payment = payments_db.get(transaction_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@app.get("/payments/by-order/{order_id}")
def get_payment_by_order(order_id: str):
    """Tra cứu thông tin payment theo order_id."""
    transaction_id = payments_by_order.get(order_id)
    if not transaction_id:
        raise HTTPException(status_code=404, detail="Payment not found for this order")
    return payments_db[transaction_id]