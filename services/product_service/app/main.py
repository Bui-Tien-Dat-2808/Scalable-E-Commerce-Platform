import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, Float, Integer, String
from sqlalchemy.orm import Session

from services.common.database import Base, engine, get_db
from services.common.consul import consul_client

SERVICE_NAME = os.getenv("SERVICE_NAME", "product-service")
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))
INSTANCE_ID = f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'default')}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed data trước
    from services.common.database import SessionLocal as _SL
    with _SL() as _db:
        _seed_products(_db)
        
    # Startup: Đăng ký với Consul
    consul_client.register_service(SERVICE_NAME, INSTANCE_ID, SERVICE_HOST, SERVICE_PORT)
    yield
    # Shutdown: Huỷ đăng ký khỏi Consul
    consul_client.deregister_service(INSTANCE_ID)


app = FastAPI(title="Product Catalog Service", version="1.0.0", lifespan=lifespan)


# ── Model ─────────────────────────────────────────────────────────────────────

class ProductModel(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)


Base.metadata.create_all(bind=engine)


def _seed_products(db: Session):
    """Thêm sản phẩm mẫu nếu DB đang rỗng."""
    if db.query(ProductModel).count() == 0:
        db.add_all([
            ProductModel(name="Laptop", price=999.99, stock=10),
            ProductModel(name="Smartphone", price=499.99, stock=20),
        ])
        db.commit()


# Seed function is now called inside lifespan context manager


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProductCreateRequest(BaseModel):
    name: str
    price: float
    stock: int


class ProductUpdateRequest(BaseModel):
    name: str
    price: float
    stock: int


class StockDeductRequest(BaseModel):
    quantity: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_active_product(product_id: int, db: Session) -> ProductModel:
    product = db.query(ProductModel).filter(
        ProductModel.id == product_id,
        ProductModel.is_active == True,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "product-service", "message": "Product service is running"}


@app.get("/health")
def health_check():
    return {"service": "product-service", "status": "ok"}


@app.post("/products", status_code=201)
def create_product(payload: ProductCreateRequest, db: Session = Depends(get_db)):
    product = ProductModel(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"id": product.id, "name": product.name, "price": product.price,
            "stock": product.stock, "is_active": product.is_active}


@app.get("/products")
def list_products(db: Session = Depends(get_db)):
    products = db.query(ProductModel).filter(ProductModel.is_active == True).all()
    return {"products": [
        {"id": p.id, "name": p.name, "price": p.price, "stock": p.stock, "is_active": p.is_active}
        for p in products
    ]}


@app.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = _get_active_product(product_id, db)
    return {"id": product.id, "name": product.name, "price": product.price,
            "stock": product.stock, "is_active": product.is_active}


@app.put("/products/{product_id}")
def update_product(product_id: int, payload: ProductUpdateRequest, db: Session = Depends(get_db)):
    product = _get_active_product(product_id, db)
    product.name = payload.name
    product.price = payload.price
    product.stock = payload.stock
    db.commit()
    db.refresh(product)
    return {"id": product.id, "name": product.name, "price": product.price,
            "stock": product.stock, "is_active": product.is_active}


@app.patch("/products/{product_id}/deduct-stock")
def deduct_stock(product_id: int, payload: StockDeductRequest, db: Session = Depends(get_db)):
    """Trừ tồn kho khi tạo order. Trả 409 nếu không đủ hàng."""
    product = _get_active_product(product_id, db)
    if product.stock < payload.quantity:
        raise HTTPException(
            status_code=409,
            detail=f"Insufficient stock for product {product_id}: available={product.stock}, requested={payload.quantity}",
        )
    product.stock -= payload.quantity
    db.commit()
    db.refresh(product)
    return {"product_id": product_id, "deducted": payload.quantity, "remaining_stock": product.stock}


@app.delete("/products/{product_id}")
def soft_delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    db.commit()
    db.refresh(product)
    return {"message": "Product soft deleted", "product": {
        "id": product.id, "name": product.name, "is_active": product.is_active
    }}
