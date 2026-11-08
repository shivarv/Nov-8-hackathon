from fastapi import APIRouter, HTTPException, status

from app import shoppers
from app.deps import DbSession, Recommender
from app.models import Cart, CartItem, Order, OrderItem, Product
from app.schemas import CartItemOut, CartOut, CheckoutOut, ProductOut, SetQuantityIn

router = APIRouter(prefix="/carts", tags=["carts"])


def _get_cart(db: DbSession, cart_id: str) -> Cart:
    cart = db.get(Cart, cart_id)
    if cart is None:
        raise HTTPException(404, "Cart not found")
    return cart


def _cart_out(cart: Cart) -> CartOut:
    items = [
        CartItemOut(product=ProductOut.model_validate(ci.product), quantity=ci.quantity)
        for ci in cart.items
    ]
    return CartOut(
        id=cart.id,
        items=items,
        item_count=sum(i.quantity for i in items),
        subtotal_cents=sum(i.quantity * i.product.price_cents for i in items),
    )


@router.post("", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def create_cart(db: DbSession):
    cart = Cart()
    db.add(cart)
    db.commit()
    return _cart_out(cart)


@router.get("/{cart_id}", response_model=CartOut)
def get_cart(cart_id: str, db: DbSession):
    return _cart_out(_get_cart(db, cart_id))


@router.put("/{cart_id}/items/{product_id}", response_model=CartOut)
def set_item_quantity(cart_id: str, product_id: int, body: SetQuantityIn, db: DbSession):
    """Set an item's quantity (idempotent). Quantity 0 removes it."""
    cart = _get_cart(db, cart_id)
    if db.get(Product, product_id) is None:
        raise HTTPException(404, "Product not found")

    existing = next((ci for ci in cart.items if ci.product_id == product_id), None)
    if body.quantity == 0:
        if existing:
            cart.items.remove(existing)
    elif existing:
        existing.quantity = body.quantity
    else:
        cart.items.append(CartItem(product_id=product_id, quantity=body.quantity))
    db.commit()
    db.refresh(cart)
    return _cart_out(cart)


@router.post("/{cart_id}/checkout", response_model=CheckoutOut)
def checkout(cart_id: str, db: DbSession, recommender: Recommender, shopper_id: int | None = None):
    """Turn the cart into an order and feed it to the recommender immediately.

    With `shopper_id`, the order also joins that demo shopper's history, so their
    next feed (and BehaviorGPT's next calls) see it.
    """
    cart = _get_cart(db, cart_id)
    if not cart.items:
        raise HTTPException(400, "Cart is empty")

    order = Order(
        items=[OrderItem(product_id=ci.product_id, quantity=ci.quantity) for ci in cart.items]
    )
    db.add(order)
    product_ids = [ci.product_id for ci in cart.items]
    item_count = sum(ci.quantity for ci in cart.items)
    cart.items.clear()
    db.commit()

    recommender.add_basket(product_ids)
    if shopper_id is not None and (shopper := shoppers.get(shopper_id)) is not None:
        shopper.add_order(product_ids, shopper.now())
    return CheckoutOut(order_id=order.id, item_count=item_count)
