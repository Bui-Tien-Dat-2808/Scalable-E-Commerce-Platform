import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, Float, Integer, String
from sqlalchemy.orm import Session
from typing import Optional

from services.common.database import Base, engine, get_db, SessionLocal
from services.common.consul import consul_client
from services.common.security import require_admin

from prometheus_fastapi_instrumentator import Instrumentator
from services.common.logging import setup_logger

SERVICE_NAME = os.getenv("SERVICE_NAME", "product-service")
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))
INSTANCE_ID = f"{SERVICE_NAME}-{os.getenv('HOSTNAME', 'default')}"

logger = setup_logger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up product-service...")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as _db:
        _seed_products(_db)
    consul_client.register_service(SERVICE_NAME, INSTANCE_ID, SERVICE_HOST, SERVICE_PORT)
    yield
    logger.info("Shutting down product-service...")
    consul_client.deregister_service(INSTANCE_ID)


app = FastAPI(title="Product Catalog Service", version="1.0.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


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


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProductCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)


class ProductUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)


class StockDeductRequest(BaseModel):
    quantity: int = Field(..., ge=1)


class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    stock: int
    is_active: bool


class PaginatedProductResponse(BaseModel):
    data: list[ProductResponse]
    total: int
    page: int
    limit: int
    pages: int


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_active_product(product_id: int, db: Session) -> ProductModel:
    product = db.query(ProductModel).filter(
        ProductModel.id == product_id,
        ProductModel.is_active == True,  # noqa: E712
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


def _to_response(p: ProductModel) -> ProductResponse:
    return ProductResponse(id=p.id, name=p.name, price=p.price, stock=p.stock, is_active=p.is_active)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "product-service", "message": "Product service is running"}


@app.get("/health")
def health_check():
    return {"service": "product-service", "status": "ok"}


@app.get("/products", response_model=PaginatedProductResponse, tags=["Products"])
def list_products(
    page: int = Query(1, ge=1, description="Số trang (bắt đầu từ 1)"),
    limit: int = Query(20, ge=1, le=100, description="Số item mỗi trang (tối đa 100)"),
    name: Optional[str] = Query(None, description="Lọc theo tên (tìm kiếm gần đúng)"),
    min_price: Optional[float] = Query(None, ge=0, description="Giá tối thiểu"),
    max_price: Optional[float] = Query(None, ge=0, description="Giá tối đa"),
    in_stock: Optional[bool] = Query(None, description="Chỉ hiện sản phẩm còn hàng"),
    db: Session = Depends(get_db),
):
    query = db.query(ProductModel).filter(ProductModel.is_active == True)  # noqa: E712

    if name:
        query = query.filter(ProductModel.name.ilike(f"%{name}%"))
    if min_price is not None:
        query = query.filter(ProductModel.price >= min_price)
    if max_price is not None:
        query = query.filter(ProductModel.price <= max_price)
    if in_stock is True:
        query = query.filter(ProductModel.stock > 0)
    elif in_stock is False:
        query = query.filter(ProductModel.stock == 0)

    total = query.count()
    pages = max(1, -(-total // limit))  # ceiling division
    products = query.offset((page - 1) * limit).limit(limit).all()

    return PaginatedProductResponse(
        data=[_to_response(p) for p in products],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@app.get("/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    return _to_response(_get_active_product(product_id, db))


@app.post("/products", status_code=201, response_model=ProductResponse, tags=["Products"])
def create_product(
    payload: ProductCreateRequest,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    product = ProductModel(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return _to_response(product)


@app.put("/products/{product_id}", response_model=ProductResponse, tags=["Products"])
def update_product(
    product_id: int,
    payload: ProductUpdateRequest,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    product = _get_active_product(product_id, db)
    product.name = payload.name
    product.price = payload.price
    product.stock = payload.stock
    db.commit()
    db.refresh(product)
    return _to_response(product)


@app.patch("/products/{product_id}/deduct-stock", tags=["Products"])
def deduct_stock(product_id: int, payload: StockDeductRequest, db: Session = Depends(get_db)):
    """Trừ tồn kho khi tạo order. Internal call — không yêu cầu admin."""
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


@app.delete("/products/{product_id}", tags=["Products"])
def soft_delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    product = db.query(ProductModel).filter(ProductModel.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    db.commit()
    db.refresh(product)
    return {"message": "Product soft deleted", "product": _to_response(product)}
