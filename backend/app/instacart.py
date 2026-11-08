"""Load the real Instacart catalog and a sample of real orders into an empty DB.

Products: all of archive/products.csv, with department and aisle names, a price
from data/product_prices.csv, an emoji per department, and a popularity count.

Orders: a random sample of `n_orders` real Instacart orders (each shopper's most
recent order, the "train" set), with their shopper id. They are the history the
bought-together model learns from.
"""

import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Product

DEPARTMENT_EMOJI = {
    "alcohol": "🍷",
    "babies": "🍼",
    "bakery": "🍞",
    "beverages": "🥤",
    "breakfast": "🥣",
    "bulk": "🥜",
    "canned goods": "🥫",
    "dairy eggs": "🥛",
    "deli": "🥪",
    "dry goods pasta": "🍝",
    "frozen": "🧊",
    "household": "🧽",
    "international": "🌮",
    "meat seafood": "🥩",
    "pantry": "🫙",
    "personal care": "🧴",
    "pets": "🐾",
    "produce": "🥬",
    "snacks": "🍿",
}
DEFAULT_EMOJI = "🛒"
REQUIRED_FILES = (
    "products.csv",
    "aisles.csv",
    "departments.csv",
    "orders.csv",
    "order_products__train.csv",
)


def available(instacart_dir: str, prices_csv: str) -> bool:
    d = Path(instacart_dir)
    return all((d / f).is_file() for f in REQUIRED_FILES) and Path(prices_csv).is_file()


def _rows(path: Path) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _title(s: str) -> str:
    return s.title()


def load(db: Session, instacart_dir: str, prices_csv: str, n_orders: int, seed: int = 42) -> int:
    """Insert products and a sample of real orders. Returns the number of orders loaded."""
    d = Path(instacart_dir)
    aisles = {r["aisle_id"]: r["aisle"] for r in _rows(d / "aisles.csv")}
    departments = {r["department_id"]: r["department"] for r in _rows(d / "departments.csv")}
    prices = {r["product_id"]: r["price_usd"] for r in _rows(Path(prices_csv))}

    # Real orders: the train set holds each shopper's most recent order.
    baskets: defaultdict[int, list[int]] = defaultdict(list)
    with open(d / "order_products__train.csv") as f:
        next(f)
        for line in f:
            order_id, product_id, _, _ = line.split(",", 3)
            baskets[int(order_id)].append(int(product_id))
    popularity = Counter(pid for items in baskets.values() for pid in items)

    order_ids = sorted(baskets)
    sample = sorted(random.Random(seed).sample(order_ids, min(n_orders, len(order_ids))))
    user_of = {
        int(r["order_id"]): int(r["user_id"])
        for r in _rows(d / "orders.csv")
        if r["eval_set"] == "train"
    }

    db.execute(
        insert(Product),
        [
            {
                "id": int(p["product_id"]),
                "name": p["product_name"][:200],
                "department": _title(departments[p["department_id"]]),
                "aisle": _title(aisles[p["aisle_id"]]),
                "price_cents": round(float(prices.get(p["product_id"], "3.49")) * 100),
                "emoji": DEPARTMENT_EMOJI.get(departments[p["department_id"]], DEFAULT_EMOJI),
                "popularity": popularity.get(int(p["product_id"]), 0),
            }
            for p in _rows(d / "products.csv")
        ],
    )
    # Let the DB assign order ids (explicit ids would leave Postgres's sequence behind,
    # and orders placed later in the app would collide with them).
    new_ids = db.scalars(
        insert(Order).returning(Order.id, sort_by_parameter_order=True),
        [{"user_id": user_of.get(oid)} for oid in sample],
    ).all()
    db.execute(
        insert(OrderItem),
        [
            {"order_id": new_id, "product_id": pid}
            for new_id, oid in zip(new_ids, sample, strict=True)
            for pid in dict.fromkeys(baskets[oid])
        ],
    )
    db.commit()
    return len(sample)
