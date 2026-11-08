import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app import images
from app.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    department: Mapped[str] = mapped_column(String(60), index=True)
    aisle: Mapped[str] = mapped_column(String(60))
    price_cents: Mapped[int]
    emoji: Mapped[str] = mapped_column(String(16))
    # Times bought in the loaded order history; lists show popular products first.
    popularity: Mapped[int] = mapped_column(default=0, index=True)

    @property
    def image_url(self) -> str | None:
        """Photo URL from data/*_images.csv (not stored in the DB)."""
        return images.image_for(self.id, self.aisle)


class Order(Base):
    """A completed basket. Order history is the training data for the recommender."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Instacart shopper id for imported orders; empty for orders placed in the app.
    user_id: Mapped[int | None] = mapped_column(index=True, default=None)
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(default=1)


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    items: Mapped[list["CartItem"]] = relationship(
        cascade="all, delete-orphan", order_by="[CartItem.added_at, CartItem.product_id]"
    )


class CartItem(Base):
    __tablename__ = "cart_items"

    cart_id: Mapped[str] = mapped_column(ForeignKey("carts.id"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    quantity: Mapped[int]
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product: Mapped[Product] = relationship(lazy="joined")
