from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Product Catalog Service", version="1.0.0")


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


class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    stock: int
    is_active: bool


products_db = [
    {"id": 1, "name": "Laptop", "price": 999.99, "stock": 10, "is_active": True},
    {"id": 2, "name": "Smartphone", "price": 499.99, "stock": 20, "is_active": True},
]


def find_product(product_id: int) -> dict | None:
    return next((product for product in products_db if product["id"] == product_id), None)


@app.get("/")
def root():
    return {"service": "product-service", "message": "Product service is running"}


@app.get("/health")
def health_check():
    return {"service": "product-service", "status": "ok"}


@app.post("/products", status_code=201)
def create_product(payload: ProductCreateRequest):
    product = ProductResponse(id=len(products_db) + 1, is_active=True, **payload.model_dump())
    products_db.append(product.model_dump())
    return product.model_dump()


@app.get("/products")
def list_products():
    return {"products": [product for product in products_db if product["is_active"]]}


@app.get("/products/{product_id}")
def get_product(product_id: int):
    product = find_product(product_id)
    if not product or not product["is_active"]:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.put("/products/{product_id}")
def update_product(product_id: int, payload: ProductUpdateRequest):
    product = find_product(product_id)
    if not product or not product["is_active"]:
        raise HTTPException(status_code=404, detail="Product not found")

    product.update(payload.model_dump())
    return product


@app.patch("/products/{product_id}/deduct-stock")
def deduct_stock(product_id: int, payload: StockDeductRequest):
    """Trừ tồn kho khi tạo order. Trả 409 nếu không đủ hàng."""
    product = find_product(product_id)
    if not product or not product["is_active"]:
        raise HTTPException(status_code=404, detail="Product not found")
    if product["stock"] < payload.quantity:
        raise HTTPException(
            status_code=409,
            detail=f"Insufficient stock for product {product_id}: available={product['stock']}, requested={payload.quantity}",
        )

    product["stock"] -= payload.quantity
    return {"product_id": product_id, "deducted": payload.quantity, "remaining_stock": product["stock"]}


@app.delete("/products/{product_id}")
def soft_delete_product(product_id: int):
    product = find_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product["is_active"] = False
    return {"message": "Product soft deleted", "product": product}
