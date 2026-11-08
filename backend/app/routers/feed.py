from fastapi import APIRouter, HTTPException

from app import feed, shoppers
from app.deps import BehaviorGPT, DbSession, Recommender
from app.models import Cart
from app.schemas import FeedOut, ShopperOut

router = APIRouter(tags=["feed"])


@router.get("/shoppers", response_model=list[ShopperOut])
def list_shoppers():
    """Real Instacart shoppers to shop as (data/demo_shoppers.json)."""
    return [
        ShopperOut(
            id=s.id, label=s.label, blurb=s.blurb, usual_day=s.usual_day, n_orders=s.n_orders
        )
        for s in shoppers.all_shoppers()
    ]


@router.get("/feed", response_model=FeedOut)
def get_feed(
    shopper_id: int,
    db: DbSession,
    recommender: Recommender,
    bgpt: BehaviorGPT,
    cart_id: str | None = None,
):
    """The shopper's walk through the store, given what is in their cart now."""
    shopper = shoppers.get(shopper_id)
    if shopper is None:
        raise HTTPException(404, "Shopper not found")
    cart_items: list[int] = []
    if cart_id:
        cart = db.get(Cart, cart_id)
        if cart is None:
            raise HTTPException(404, "Cart not found")
        cart_items = [ci.product_id for ci in cart.items]  # in the order they were added
    return feed.build(db, shopper, cart_items, bgpt, recommender)
