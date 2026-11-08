import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Order, OrderItem, Product
from app.seed import instacart_available, read_instacart_orders, seed_if_empty

pytestmark = pytest.mark.skipif(not instacart_available(), reason="no data/instacart files")


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_seeds_real_catalog_and_orders(db):
    assert seed_if_empty(db, "instacart", n_orders=500) == "Instacart catalog and 500 real orders"
    assert db.scalar(select(func.count()).select_from(Product)) == 3000
    assert db.scalar(select(func.count()).select_from(Order)) == 500
    assert db.scalar(select(func.count(func.distinct(Order.user_id)))) > 1

    # every order line points at a catalog product, and prices are real numbers
    orphans = select(func.count()).select_from(OrderItem).where(
        OrderItem.product_id.not_in(select(Product.id))
    )
    assert db.scalar(orphans) == 0
    assert db.scalar(select(func.min(Product.price_cents))) > 0

    banana = db.scalar(select(Product).where(Product.name == "Banana"))
    assert banana.id == 24852  # Instacart product id is kept
    assert banana.department == "Produce" and banana.emoji == "🍌"
    assert banana.image_url is None  # produce uses its emoji, not a shopper photo
    # Banana is Instacart's best seller, so it has the highest popularity.
    assert banana.popularity == db.scalar(select(func.max(Product.popularity)))

    assert seed_if_empty(db, "instacart") is None  # never re-seeds a non-empty DB


def test_order_limit_keeps_whole_orders():
    first = read_instacart_orders(50)
    assert len(first) == 50
    assert read_instacart_orders(100)[:50] == first
    assert all(items for _, items in first)
