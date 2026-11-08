"""New shoppers: people who start in the app with no purchase history.

Each one is a stored profile (shopper_profiles) and, while the backend runs, a
Shopper registered next to the demo shoppers, so search, the planner, the feed and
checkout work for them unchanged. Everything they do with products is stored as a
signal (shopper_signals): what they looked at and for how long, what they clicked
open, added, removed and bought. Their orders are Orders with user_id = their
shopper id. On startup `load_all` rebuilds them all from the database.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import shoppers
from app.models import Order, OrderItem, ShopperProfile, ShopperSignal
from app.shoppers import PROFILE_ID_BASE, Shopper

LABEL = "New shopper"
BLURB = "No history yet. What you look at, click and buy builds your For you tab."
SIGNAL_KINDS = ("view", "open", "add", "remove", "purchase")


def shopper_id(profile_id: int) -> int:
    return PROFILE_ID_BASE + profile_id


def profile_id(shopper_id: int) -> int:
    return shopper_id - PROFILE_ID_BASE


def _build(profile: ShopperProfile, orders: list[tuple[datetime, list[int]]]) -> Shopper:
    shopper = Shopper(
        id=shopper_id(profile.id),
        label=profile.label or LABEL,
        blurb=profile.blurb or BLURB,
        usual_day="",
        orders=[],
    )
    for at, items in orders:
        shopper.add_order(items, at if at.tzinfo else at.replace(tzinfo=UTC))
    return shopper


def _orders(db: Session, sid: int) -> list[tuple[datetime, list[int]]]:
    rows = db.execute(
        select(Order.id, Order.created_at, OrderItem.product_id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(Order.user_id == sid)
        .order_by(Order.id)
    )
    by_order: dict[int, tuple[datetime, list[int]]] = {}
    for order_id, at, product_id in rows:
        by_order.setdefault(order_id, (at or datetime.now(UTC), []))[1].append(product_id)
    return list(by_order.values())


def create(db: Session) -> Shopper:
    profile = ShopperProfile()
    db.add(profile)
    db.commit()
    shopper = _build(profile, [])
    shoppers.register(shopper)
    return shopper


def load_all(db: Session) -> int:
    """Register every stored new shopper, with their orders. Returns how many."""
    profiles = db.scalars(select(ShopperProfile)).all()
    for profile in profiles:
        shoppers.register(_build(profile, _orders(db, shopper_id(profile.id))))
    return len(profiles)


def record(db: Session, sid: int, kind: str, product_id: int, dwell_ms: int = 0) -> None:
    """Store one signal for a new shopper (no-op for anyone else). Caller commits."""
    if not shoppers.is_new(sid) or kind not in SIGNAL_KINDS:
        return
    db.add(
        ShopperSignal(
            profile_id=profile_id(sid), product_id=product_id, kind=kind, dwell_ms=dwell_ms
        )
    )


def signals(db: Session, sid: int) -> list[ShopperSignal]:
    return list(
        db.scalars(
            select(ShopperSignal)
            .where(ShopperSignal.profile_id == profile_id(sid))
            .order_by(ShopperSignal.id)
        )
    )
