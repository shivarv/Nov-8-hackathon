from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import seedfile
from app.db import Base
from app.models import Order, OrderItem, Product
from app.seed import seed_if_empty


def _snapshot(db: Session):
    products = [
        (p.id, p.name, p.department, p.aisle, p.price_cents, p.emoji, p.popularity)
        for p in db.scalars(select(Product).order_by(Product.id))
    ]
    orders: dict[int, tuple[int | None, set[int]]] = {
        o.id: (o.user_id, set()) for o in db.scalars(select(Order))
    }
    for oid, pid in db.execute(select(OrderItem.order_id, OrderItem.product_id)):
        orders[oid][1].add(pid)
    return products, [(u, frozenset(items)) for _, (u, items) in sorted(orders.items())]


def test_seed_round_trip(tmp_path):
    source = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(source)
    with Session(source) as db:
        seed_if_empty(db, 200)
        db.execute(select(Order)).first()
        expected = _snapshot(db)
        counts = seedfile.dump(db, str(tmp_path / "seed.json.xz"))
    assert counts["orders"] == 200 and counts["products"] == len(expected[0])

    target = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(target)
    with Session(target) as db:
        assert seedfile.load(db, str(tmp_path / "seed.json.xz")) == 200
        assert _snapshot(db) == expected
