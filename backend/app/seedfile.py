"""The pre-built seed: everything the app loads from Instacart, in one ~1 MB file.

data/seed.json.xz holds the catalog (49,688 products with department, aisle,
estimated price, emoji and popularity already computed) and the 20,000 real orders
the bought-together model trains on, stored column by column and xz-compressed.
It is what `instacart.load` would put in the database, so a deployment doesn't need
the raw dataset (archive/, 680 MB). Build it with:

    backend/.venv/bin/python scripts/build_seed.py

The recommender is still trained at startup (about 2 s): its trained form is ~13x
larger than these orders.
"""

import json
import lzma
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Product

VERSION = 1


def available(path: str) -> bool:
    return Path(path).is_file()


def dump(db: Session, path: str) -> dict:
    """Write the database's products and orders to `path`. Returns the counts."""
    products = db.scalars(select(Product).order_by(Product.id)).all()
    departments = sorted({p.department for p in products})
    aisles = sorted({p.aisle for p in products})
    emojis = sorted({p.emoji for p in products})
    orders: dict[int, list[int | None]] = {
        o.id: [o.user_id] for o in db.scalars(select(Order).order_by(Order.id))
    }
    for order_id, product_id in db.execute(
        select(OrderItem.order_id, OrderItem.product_id).order_by(
            OrderItem.order_id, OrderItem.product_id
        )
    ):
        orders[order_id].append(product_id)
    ids = [p.id for p in products]
    seed = {
        "version": VERSION,
        "departments": departments,
        "aisles": aisles,
        "emojis": emojis,
        # products, one list per column; ids as differences (mostly 1)
        "id_delta": ids[:1] + [b - a for a, b in zip(ids, ids[1:], strict=False)],
        "name": [p.name for p in products],
        "department": [departments.index(p.department) for p in products],
        "aisle": [aisles.index(p.aisle) for p in products],
        "price_cents": [p.price_cents for p in products],
        "emoji": [emojis.index(p.emoji) for p in products],
        "popularity": [p.popularity for p in products],
        # orders: [shopper id, product id, product id, ...]
        "orders": list(orders.values()),
    }
    raw = json.dumps(seed, separators=(",", ":"), ensure_ascii=False).encode()
    Path(path).write_bytes(lzma.compress(raw, preset=9 | lzma.PRESET_EXTREME))
    return {"products": len(products), "orders": len(orders)}


def load(db: Session, path: str) -> int:
    """Insert the seed's products and orders. Returns the number of orders loaded."""
    seed = json.loads(lzma.decompress(Path(path).read_bytes()))
    if seed.get("version") != VERSION:
        raise RuntimeError(f"{path}: seed version {seed.get('version')}, expected {VERSION}")
    ids, pid = [], 0
    for d in seed["id_delta"]:
        pid += d
        ids.append(pid)
    db.execute(
        insert(Product),
        [
            {
                "id": ids[i],
                "name": seed["name"][i],
                "department": seed["departments"][seed["department"][i]],
                "aisle": seed["aisles"][seed["aisle"][i]],
                "price_cents": seed["price_cents"][i],
                "emoji": seed["emojis"][seed["emoji"][i]],
                "popularity": seed["popularity"][i],
            }
            for i in range(len(ids))
        ],
    )
    orders = seed["orders"]
    # Let the DB assign order ids (explicit ids would leave Postgres's sequence behind).
    new_ids = db.scalars(
        insert(Order).returning(Order.id, sort_by_parameter_order=True),
        [{"user_id": o[0]} for o in orders],
    ).all()
    db.execute(
        insert(OrderItem),
        [
            {"order_id": new_id, "product_id": p}
            for new_id, o in zip(new_ids, orders, strict=True)
            for p in o[1:]
        ],
    )
    db.commit()
    return len(orders)
