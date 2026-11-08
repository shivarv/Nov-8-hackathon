from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    department: str
    aisle: str
    price_cents: int
    emoji: str
    image_url: str | None = None


class CartItemOut(BaseModel):
    product: ProductOut
    quantity: int


class CartOut(BaseModel):
    id: str
    items: list[CartItemOut]
    item_count: int
    subtotal_cents: int


class SetQuantityIn(BaseModel):
    quantity: int = Field(ge=0, le=99, description="0 removes the item")


class CheckoutOut(BaseModel):
    order_id: int
    item_count: int


class ShopperOut(BaseModel):
    id: int
    label: str
    blurb: str
    usual_day: str
    usual_hour: int = 12
    usual_gap_days: int = 7
    n_orders: int
    days_ahead: int = 0
    # A new shopper who started in the app (app/newusers.py), not an Instacart shopper.
    is_new: bool = False
    # New shopper: True once their entry (label, blurb) has been generated from behaviour.
    has_entry: bool = False


Confidence = Literal["sure", "good", "explore"]


class FeedItemOut(BaseModel):
    product: ProductOut
    # usual: they buy it often · pairs: goes with the basket · new: never bought it ·
    # due: a regular they haven't bought lately · treat: small extra for the checkout
    tag: Literal["usual", "pairs", "new", "due", "treat", "foryou"]
    reason: str
    confidence: float = Field(ge=0, le=1)


class FeedSectionOut(BaseModel):
    key: str
    kind: Literal["regulars", "pairs", "mission", "aisle", "due", "treat", "foryou"]
    title: str
    subtitle: str
    confidence: Confidence
    aisle_number: int | None = None
    items: list[FeedItemOut]


class FeedOut(BaseModel):
    shopper: ShopperOut
    sections: list[FeedSectionOut]
    model: Literal["behaviorgpt", "fallback"]
    # Days since their last order on the shopper's timeline, and how far the demo has
    # moved their clock forward ("next visit").
    days_since_last_order: int | None = None
    days_ahead: int = 0


class RecommendationOut(BaseModel):
    product: ProductOut
    score: float
    source: Literal["behaviorgpt", "bought_together", "popular"]
    reason: str


class SearchOut(BaseModel):
    query: str
    model: Literal["behaviorgpt", "fallback"]
    # The shopper's own past items for this query, best first ("your usual milk").
    yours: list[FeedItemOut]
    # The whole catalog for this query, personalized by history and cart.
    results: list[FeedItemOut]
    # Not about the query: what fits their past orders and the cart.
    for_you: list[FeedItemOut]
    for_you_title: str
    # The same query for an anonymous shopper (no history): what personalization changed.
    generic: list[FeedItemOut] = []


class ReplayScore(BaseModel):
    name: str
    description: str
    hits: int  # items of the real next order in this strategy's top `k`
    k: int


class ReplayOut(BaseModel):
    """The shopper's real next order (Instacart held it out; the model never saw it),
    and how many of its items each way of picking 10 products would have found."""

    items: list[int]
    n: int
    days_since_prior: int | None
    scoreboard: list[ReplayScore]
    # Of the next order's items, how many the home page shows anywhere (empty cart).
    on_home_page: int


class NextVisitOut(BaseModel):
    days_ahead: int


class PlanIn(BaseModel):
    shopper_id: int
    cart_id: str | None = None
    request: str = Field(min_length=3, max_length=200)


class PlanPick(BaseModel):
    need_key: str
    label: str  # the need, as planned ("Tortillas")
    quantity: int
    item: FeedItemOut  # the product; its reason is the note for the shopper


class PlanOut(BaseModel):
    """A basket built for a request: Claude planned and composed it, BehaviorGPT found
    each pick among this shopper's candidates, the server checked it."""

    request: str
    title: str
    summary: str
    tip: str = ""
    budget_cents: int | None = None
    total_cents: int
    picks: list[PlanPick]
    # Per need, the other candidates (for swapping a pick).
    alternatives: dict[str, list[ProductOut]] = {}
    by: Literal["claude", "rules"]


# --- new shoppers: what they do, their pattern, their For you tab (app/foryou.py) ------


class SignalIn(BaseModel):
    product_id: int
    kind: Literal["view", "open"]  # adds, removes and purchases are recorded by the cart
    dwell_ms: int = Field(ge=0, le=600_000)


class PatternTagOut(BaseModel):
    key: Literal["organic", "budget", "premium"]
    label: str  # "Organic seeker"
    strength: Literal["strong", "leaning"]
    why: str


class PatternOut(BaseModel):
    """How a new shopper shops. Leanings run from -1 to 1 (0 = like a typical shopper)."""

    method: Literal["behaviorgpt", "signals"]  # "behaviorgpt": it refereed the tags
    leanings: dict[str, float]  # organic / budget / premium, from their attention
    # BehaviorGPT's lean per trait vs typical shoppers (empty without it)
    model_leanings: dict[str, float] = {}
    tags: list[PatternTagOut]
    top_departments: list[str]  # where their attention goes, most first
    products_seen: int
    seconds_looking: float
    clicks: int  # products opened for a closer look
    adds: int
    purchases: int
    enough: bool  # enough behaviour to decide anything


class EntryOut(BaseModel):
    """The user entry generated for a new shopper once there is enough data."""

    label: str
    blurb: str
    generated_at: datetime
    just_generated: bool = False


class ForYouOut(BaseModel):
    shopper: ShopperOut
    pattern: PatternOut
    entry: EntryOut | None = None
    sections: list[FeedSectionOut]
    model: Literal["behaviorgpt", "fallback"]
