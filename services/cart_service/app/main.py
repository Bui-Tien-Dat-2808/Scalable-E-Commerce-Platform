import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db
from services.common.security import get_current_user_id
from services.common.consul import consul_client

from prometheus_fastapi_instrumentator import Instrumentator
from services.common.logging import setup_logger

SERVICE_NAME = os.getenv("SERVICE_NAME", "cart-service")
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8002"))
INSTANCE_ID = f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'default')}"

logger = setup_logger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up cart-service...")
    # Startup: Đăng ký với Consul
    consul_client.register_service(SERVICE_NAME, INSTANCE_ID, SERVICE_HOST, SERVICE_PORT)
    yield
    logger.info("Shutting down cart-service...")
    # Shutdown: Huỷ đăng ký khỏi Consul
    consul_client.deregister_service(INSTANCE_ID)


app = FastAPI(title="Shopping Cart Service", version="1.0.0", lifespan=lifespan)
# Expose /metrics
Instrumentator().instrument(app).expose(app)


# ── Model ─────────────────────────────────────────────────────────────────────

class CartItemModel(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)


Base.metadata.create_all(bind=engine)


# ── Schemas ───────────────────────────────────────────────────────────────────

class CartItemRequest(BaseModel):
    product_id: int = Field(..., gt=0, description="Product ID must be greater than zero")
    quantity: int = Field(..., gt=0, description="Quantity must be greater than zero")


class CartUpdateRequest(BaseModel):
    quantity: int = Field(..., gt=0, description="Quantity must be greater than zero")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_cart_response(user_id: str, db: Session) -> dict:
    items = db.query(CartItemModel).filter(CartItemModel.user_id == user_id).all()
    return {
        "user_id": user_id,
        "items": [{"product_id": i.product_id, "quantity": i.quantity} for i in items],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "cart-service", "message": "Cart service is running"}


@app.get("/health")
def health_check():
    return {"service": "cart-service", "status": "ok"}


@app.get("/cart")
def get_cart(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return _build_cart_response(user_id, db)


@app.post("/cart/items")
def add_to_cart(
    payload: CartItemRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    existing = db.query(CartItemModel).filter(
        CartItemModel.user_id == user_id,
        CartItemModel.product_id == payload.product_id,
    ).first()
    if existing:
        existing.quantity += payload.quantity
    else:
        db.add(CartItemModel(user_id=user_id, product_id=payload.product_id, quantity=payload.quantity))
    db.commit()
    return _build_cart_response(user_id, db)


@app.put("/cart/items/{product_id}")
def update_cart_item(
    product_id: int,
    payload: CartUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    item = db.query(CartItemModel).filter(
        CartItemModel.user_id == user_id,
        CartItemModel.product_id == product_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Product not found in cart")
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")
    item.quantity = payload.quantity
    db.commit()
    return _build_cart_response(user_id, db)


@app.delete("/cart/items/{product_id}")
def delete_cart_item(
    product_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    item = db.query(CartItemModel).filter(
        CartItemModel.user_id == user_id,
        CartItemModel.product_id == product_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Product not found in cart")
    db.delete(item)
    db.commit()
    return _build_cart_response(user_id, db)
