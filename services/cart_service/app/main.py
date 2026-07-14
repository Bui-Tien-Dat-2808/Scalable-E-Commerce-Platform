from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from services.common.security import get_current_user_id

app = FastAPI(title="Shopping Cart Service", version="1.0.0")


class CartItemRequest(BaseModel):
    product_id: int
    quantity: int


class CartUpdateRequest(BaseModel):
    quantity: int


carts_db: dict[str, dict[int, int]] = {}


def build_cart_response(user_id: str) -> dict:
    items = [
        {"product_id": product_id, "quantity": quantity}
        for product_id, quantity in carts_db.get(user_id, {}).items()
    ]
    return {"user_id": user_id, "items": items}


@app.get("/")
def root():
    return {"service": "cart-service", "message": "Cart service is running"}


@app.get("/health")
def health_check():
    return {"service": "cart-service", "status": "ok"}


@app.get("/cart")
def get_cart(user_id: str = Depends(get_current_user_id)):
    return build_cart_response(user_id)


@app.post("/cart/items")
def add_to_cart(payload: CartItemRequest, user_id: str = Depends(get_current_user_id)):
    cart = carts_db.setdefault(user_id, {})
    cart[payload.product_id] = cart.get(payload.product_id, 0) + payload.quantity
    return build_cart_response(user_id)


@app.put("/cart/items/{product_id}")
def update_cart_item(product_id: int, payload: CartUpdateRequest, user_id: str = Depends(get_current_user_id)):
    cart = carts_db.setdefault(user_id, {})
    if product_id not in cart:
        raise HTTPException(status_code=404, detail="Product not found in cart")
    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than zero")

    cart[product_id] = payload.quantity
    return build_cart_response(user_id)


@app.delete("/cart/items/{product_id}")
def delete_cart_item(product_id: int, user_id: str = Depends(get_current_user_id)):
    cart = carts_db.setdefault(user_id, {})
    if product_id not in cart:
        raise HTTPException(status_code=404, detail="Product not found in cart")

    del cart[product_id]
    return build_cart_response(user_id)
