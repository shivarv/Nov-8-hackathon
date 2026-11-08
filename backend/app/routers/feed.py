from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app import feed, foryou, newusers, planner, replay, search, shoppers
from app.deps import BehaviorGPT, DbSession, Recommender
from app.models import Cart, Product
from app.schemas import (
    FeedOut,
    ForYouOut,
    NextVisitOut,
    PatternOut,
    PlanIn,
    PlanOut,
    ReplayOut,
    SearchOut,
    ShopperOut,
    SignalIn,
)

router = APIRouter(tags=["feed"])


@router.get("/shoppers", response_model=list[ShopperOut])
def list_shoppers():
    """Real Instacart shoppers to shop as (data/demo_shoppers.json)."""
    return [feed.shopper_out(s) for s in shoppers.all_shoppers()]


@router.post("/shoppers/new", response_model=ShopperOut, status_code=201)
def new_shopper(db: DbSession):
    """Start as a new shopper with no history; what they do is stored (app/newusers.py)."""
    return feed.shopper_out(newusers.create(db))


@router.get("/shoppers/{shopper_id}", response_model=ShopperOut)
def get_shopper(shopper_id: int):
    """One shopper: a demo shopper, or a new shopper (to continue as them)."""
    return feed.shopper_out(_shopper(shopper_id))


@router.post("/shoppers/{shopper_id}/signals", response_model=PatternOut)
def record_signals(shopper_id: int, signals: list[SignalIn], db: DbSession):
    """What a new shopper looked at and clicked open, and for how long (batched by the
    page). Returns their pattern as it stands now."""
    _shopper(shopper_id)  # 404 if unknown
    if not shoppers.is_new(shopper_id):
        raise HTTPException(400, "Only new shoppers' browsing is recorded")
    for s in signals[:500]:
        newusers.record(db, shopper_id, s.kind, s.product_id, s.dwell_ms)
    db.commit()
    b = foryou.Behaviour(newusers.signals(db, shopper_id))
    ids = set(b.shown)
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    # Signals only here (fast, called every few seconds); the For you tab asks BehaviorGPT.
    return foryou._pattern(db, b, products, foryou.medians(db), None, None)


@router.get("/shoppers/{shopper_id}/for-you", response_model=ForYouOut)
def for_you(
    shopper_id: int,
    db: DbSession,
    bgpt: BehaviorGPT,
    cart_id: str | None = None,
):
    """A new shopper's For you tab: BehaviorGPT's picks from their browsing and orders,
    their pattern, and the user entry generated once there is enough data."""
    shopper = _shopper(shopper_id)
    if not shoppers.is_new(shopper_id):
        raise HTTPException(400, "For you is built for new shoppers")
    return foryou.build(db, shopper, _cart_items(db, cart_id), bgpt)


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
