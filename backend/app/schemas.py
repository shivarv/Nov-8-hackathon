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


class RecommendationOut(BaseModel):
    product: ProductOut
    score: float
    source: Literal["bought_together", "popular"]
    reason: str
