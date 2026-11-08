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


Confidence = Literal["sure", "good", "explore"]


class FeedItemOut(BaseModel):
    product: ProductOut
    # usual: they buy it often · pairs: goes with the basket · new: never bought it ·
    # due: a regular they haven't bought lately · treat: small extra for the checkout
    tag: Literal["usual", "pairs", "new", "due", "treat"]
    reason: str
    confidence: float = Field(ge=0, le=1)


class FeedSectionOut(BaseModel):
    key: str
    kind: Literal["regulars", "pairs", "mission", "aisle", "due", "treat"]
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
