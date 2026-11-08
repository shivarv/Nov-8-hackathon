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
    n_orders: int


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
    # Shopper's own items BehaviorGPT is surest about for this basket (empty without it).
    ready_to_add: list[FeedItemOut] = []


class RecommendationOut(BaseModel):
    product: ProductOut
    score: float
    source: Literal["behaviorgpt", "bought_together", "popular"]
    reason: str
