from fastapi import APIRouter, HTTPException, Query

from app import feed, planner, replay, search, shoppers
from app.deps import BehaviorGPT, DbSession, Recommender
from app.models import Cart
from app.schemas import (
    FeedOut,
    NextVisitOut,
    PlanIn,
    PlanOut,
    ReplayOut,
    SearchOut,
    ShopperOut,
)

router = APIRouter(tags=["feed"])


@router.get("/shoppers", response_model=list[ShopperOut])
def list_shoppers():
    """Real Instacart shoppers to shop as (data/demo_shoppers.json)."""
    return [feed.shopper_out(s) for s in shoppers.all_shoppers()]


@router.get("/shoppers/{shopper_id}/replay", response_model=ReplayOut)
def get_replay(shopper_id: int, db: DbSession, recommender: Recommender, bgpt: BehaviorGPT):
    """Their real next order (never shown to the model) and how each strategy scores on it."""
    out = replay.replay(db, _shopper(shopper_id), bgpt, recommender)
    if out is None:
        raise HTTPException(404, "No held-out order for this shopper")
    return out


@router.post("/shoppers/{shopper_id}/next-visit", response_model=NextVisitOut)
def next_visit(shopper_id: int, days: int | None = Query(None, ge=1, le=60)):
    """Move the shopper's clock forward (their usual gap by default): the next trip."""
    shopper = _shopper(shopper_id)
    shopper.advance(days or shopper.usual_gap_days)
    return NextVisitOut(days_ahead=shopper.days_ahead)


@router.get("/feed", response_model=FeedOut)
def get_feed(
    shopper_id: int,
    db: DbSession,
    recommender: Recommender,
    bgpt: BehaviorGPT,
    cart_id: str | None = None,
):
    """The shopper's walk through the store, given what is in their cart now."""
    shopper = _shopper(shopper_id)
    return feed.build(db, shopper, _cart_items(db, cart_id), bgpt, recommender)


@router.get("/search", response_model=SearchOut)
def search_products(
    shopper_id: int,
    db: DbSession,
    recommender: Recommender,
    bgpt: BehaviorGPT,
    q: str = Query(min_length=1, max_length=100),
    cart_id: str | None = None,
):
    """Search the store as this shopper, with their cart: results, their usuals, and picks."""
    shopper = _shopper(shopper_id)
    return search.search(db, shopper, _cart_items(db, cart_id), q.strip(), bgpt, recommender)


@router.post("/plan", response_model=PlanOut)
def plan_basket(body: PlanIn, db: DbSession, recommender: Recommender, bgpt: BehaviorGPT):
    """Build a basket for a request ("tacos for 4 friday under $40"): Claude plans and
    composes, BehaviorGPT picks this shopper's products. Takes ~10-15 s."""
    shopper = _shopper(body.shopper_id)
    cart = _cart_items(db, body.cart_id)
    return planner.plan(shopper, cart, body.request.strip(), bgpt, recommender)


def _shopper(shopper_id: int) -> shoppers.Shopper:
    shopper = shoppers.get(shopper_id)
    if shopper is None:
        raise HTTPException(404, "Shopper not found")
    return shopper


def _cart_items(db: DbSession, cart_id: str | None) -> list[int]:
    """Product ids in the cart, in the order they were added."""
    if not cart_id:
        return []
    cart = db.get(Cart, cart_id)
    if cart is None:
        raise HTTPException(404, "Cart not found")
    return [ci.product_id for ci in cart.items]
