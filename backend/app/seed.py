"""Catalog + order history for an empty database.

Two sources:

* ``instacart`` – real data: the 3,000 most-purchased Instacart products (with estimated
  prices) and the complete order histories of ~4,000 real users. Built from the Kaggle
  dataset by ``scripts/build_instacart_seed.py`` into ``data/instacart/``.
* ``synthetic`` – a small hand-made catalog; orders are generated from shopping "missions"
  (taco night, baking, ...) plus staples and noise. Used by the tests.

The recommender only needs (order_id, product_id) rows either way.
"""

import csv
import gzip
import random
from pathlib import Path

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Product

INSTACART_DIR = Path(__file__).resolve().parent.parent / "data" / "instacart"
SYNTHETIC_DEFAULT_ORDERS = 3000

# (name, department, aisle, price_cents, emoji)
CATALOG: list[tuple[str, str, str, int, str]] = [
    # produce
    ("Bananas", "Produce", "Fresh Fruits", 79, "🍌"),
    ("Strawberries", "Produce", "Fresh Fruits", 399, "🍓"),
    ("Blueberries", "Produce", "Fresh Fruits", 449, "🫐"),
    ("Apples", "Produce", "Fresh Fruits", 129, "🍎"),
    ("Avocado", "Produce", "Fresh Fruits", 149, "🥑"),
    ("Lemons", "Produce", "Fresh Fruits", 69, "🍋"),
    ("Limes", "Produce", "Fresh Fruits", 49, "🍋"),
    ("Yellow Onion", "Produce", "Fresh Vegetables", 99, "🧅"),
    ("Garlic", "Produce", "Fresh Vegetables", 59, "🧄"),
    ("Tomatoes", "Produce", "Fresh Vegetables", 249, "🍅"),
    ("Romaine Lettuce", "Produce", "Fresh Vegetables", 279, "🥬"),
    ("Baby Spinach", "Produce", "Fresh Vegetables", 349, "🥬"),
    ("Cilantro", "Produce", "Fresh Herbs", 99, "🌿"),
    ("Jalapeño", "Produce", "Fresh Vegetables", 39, "🌶️"),
    ("Potatoes", "Produce", "Fresh Vegetables", 399, "🥔"),
    ("Carrots", "Produce", "Fresh Vegetables", 179, "🥕"),
    ("Broccoli", "Produce", "Fresh Vegetables", 229, "🥦"),
    ("Bell Pepper", "Produce", "Fresh Vegetables", 129, "🫑"),
    ("Cucumber", "Produce", "Fresh Vegetables", 99, "🥒"),
    ("Mushrooms", "Produce", "Fresh Vegetables", 299, "🍄"),
    # dairy & eggs
    ("Whole Milk", "Dairy & Eggs", "Milk", 429, "🥛"),
    ("Oat Milk", "Dairy & Eggs", "Milk", 499, "🥛"),
    ("Heavy Cream", "Dairy & Eggs", "Cream", 449, "🥛"),
    ("Large Eggs", "Dairy & Eggs", "Eggs", 449, "🥚"),
    ("Butter", "Dairy & Eggs", "Butter", 499, "🧈"),
    ("Shredded Cheddar", "Dairy & Eggs", "Cheese", 399, "🧀"),
    ("Parmesan", "Dairy & Eggs", "Cheese", 699, "🧀"),
    ("Fresh Mozzarella", "Dairy & Eggs", "Cheese", 449, "🧀"),
    ("Greek Yogurt", "Dairy & Eggs", "Yogurt", 599, "🥣"),
    ("Sour Cream", "Dairy & Eggs", "Cream", 249, "🥣"),
    # bakery
    ("Sourdough Bread", "Bakery", "Bread", 549, "🍞"),
    ("Bagels", "Bakery", "Breakfast Bakery", 449, "🥯"),
    ("Croissants", "Bakery", "Breakfast Bakery", 599, "🥐"),
    ("Flour Tortillas", "Bakery", "Tortillas", 349, "🫓"),
    ("Hamburger Buns", "Bakery", "Buns", 399, "🍔"),
    # meat & seafood
    ("Bacon", "Meat & Seafood", "Pork", 699, "🥓"),
    ("Chicken Breast", "Meat & Seafood", "Poultry", 899, "🍗"),
    ("Ground Beef", "Meat & Seafood", "Beef", 799, "🥩"),
    ("Salmon Fillet", "Meat & Seafood", "Seafood", 1299, "🐟"),
    ("Shrimp", "Meat & Seafood", "Seafood", 1099, "🦐"),
    ("Hot Dogs", "Meat & Seafood", "Hot Dogs", 499, "🌭"),
    # pantry
    ("Spaghetti", "Pantry", "Pasta", 199, "🍝"),
    ("Marinara Sauce", "Pantry", "Pasta Sauce", 449, "🥫"),
    ("Olive Oil", "Pantry", "Oils", 999, "🫒"),
    ("Jasmine Rice", "Pantry", "Grains", 349, "🍚"),
    ("Black Beans", "Pantry", "Canned Goods", 129, "🥫"),
    ("Salsa", "Pantry", "Dips & Salsa", 399, "🫙"),
    ("Taco Seasoning", "Pantry", "Spices", 149, "🧂"),
    ("Soy Sauce", "Pantry", "Asian Foods", 349, "🥢"),
    ("All-Purpose Flour", "Pantry", "Baking", 449, "🌾"),
    ("Granulated Sugar", "Pantry", "Baking", 399, "🍬"),
    ("Chocolate Chips", "Pantry", "Baking", 449, "🍫"),
    ("Baking Soda", "Pantry", "Baking", 129, "🧂"),
    ("Vanilla Extract", "Pantry", "Baking", 699, "🍦"),
    ("Peanut Butter", "Pantry", "Spreads", 449, "🥜"),
    ("Strawberry Jam", "Pantry", "Spreads", 399, "🍓"),
    ("Maple Syrup", "Pantry", "Breakfast", 899, "🍁"),
    ("Pancake Mix", "Pantry", "Breakfast", 399, "🥞"),
    ("Ketchup", "Pantry", "Condiments", 299, "🍅"),
    ("Mustard", "Pantry", "Condiments", 249, "🌭"),
    ("Granola", "Pantry", "Cereal", 549, "🥣"),
    ("Oatmeal", "Pantry", "Cereal", 449, "🥣"),
    ("Coffee Beans", "Pantry", "Coffee", 1199, "☕"),
    # snacks
    ("Tortilla Chips", "Snacks", "Chips", 399, "🌽"),
    ("Potato Chips", "Snacks", "Chips", 449, "🍟"),
    ("Popcorn", "Snacks", "Popcorn", 349, "🍿"),
    ("Dark Chocolate", "Snacks", "Candy", 349, "🍫"),
    ("Hummus", "Snacks", "Dips", 449, "🥙"),
    ("Pita Chips", "Snacks", "Crackers", 399, "🥙"),
    # beverages
    ("Orange Juice", "Beverages", "Juice", 499, "🧃"),
    ("Sparkling Water", "Beverages", "Water", 599, "💧"),
    ("Cola", "Beverages", "Soda", 699, "🥤"),
    ("Lemonade", "Beverages", "Juice", 399, "🍋"),
    ("Lager Beer", "Beverages", "Beer", 1299, "🍺"),
    ("Red Wine", "Beverages", "Wine", 1499, "🍷"),
    # frozen
    ("Frozen Pizza", "Frozen", "Pizza", 699, "🍕"),
    ("Vanilla Ice Cream", "Frozen", "Ice Cream", 599, "🍨"),
    ("Frozen Peas", "Frozen", "Vegetables", 249, "🫛"),
    # household
    ("Paper Towels", "Household", "Paper Goods", 1299, "🧻"),
    ("Dish Soap", "Household", "Cleaning", 399, "🧼"),
    ("Trash Bags", "Household", "Trash", 1099, "🗑️"),
]

# mission -> (relative weight, [(product, inclusion probability), ...])
MISSIONS: dict[str, tuple[float, list[tuple[str, float]]]] = {
    "breakfast": (
        1.0,
        [
            ("Large Eggs", 0.8),
            ("Bacon", 0.6),
            ("Sourdough Bread", 0.5),
            ("Butter", 0.5),
            ("Orange Juice", 0.5),
            ("Coffee Beans", 0.3),
        ],
    ),
    "pancakes": (
        0.6,
        [
            ("Pancake Mix", 0.9),
            ("Maple Syrup", 0.8),
            ("Butter", 0.5),
            ("Blueberries", 0.4),
            ("Large Eggs", 0.5),
            ("Whole Milk", 0.6),
        ],
    ),
    "pasta_night": (
        1.0,
        [
            ("Spaghetti", 0.9),
            ("Marinara Sauce", 0.85),
            ("Parmesan", 0.6),
            ("Garlic", 0.6),
            ("Ground Beef", 0.4),
            ("Olive Oil", 0.3),
            ("Red Wine", 0.25),
        ],
    ),
    "taco_night": (
        1.0,
        [
            ("Flour Tortillas", 0.85),
            ("Ground Beef", 0.7),
            ("Taco Seasoning", 0.7),
            ("Shredded Cheddar", 0.6),
            ("Salsa", 0.6),
            ("Sour Cream", 0.5),
            ("Avocado", 0.4),
            ("Cilantro", 0.4),
            ("Limes", 0.3),
            ("Black Beans", 0.3),
        ],
    ),
    "guac_party": (
        0.6,
        [
            ("Avocado", 0.9),
            ("Limes", 0.7),
            ("Cilantro", 0.6),
            ("Jalapeño", 0.5),
            ("Tomatoes", 0.5),
            ("Yellow Onion", 0.5),
            ("Tortilla Chips", 0.8),
            ("Lager Beer", 0.4),
        ],
    ),
    "baking": (
        0.7,
        [
            ("All-Purpose Flour", 0.9),
            ("Granulated Sugar", 0.8),
            ("Chocolate Chips", 0.7),
            ("Butter", 0.7),
            ("Large Eggs", 0.7),
            ("Baking Soda", 0.5),
            ("Vanilla Extract", 0.5),
        ],
    ),
    "salad": (
        0.9,
        [
            ("Romaine Lettuce", 0.7),
            ("Baby Spinach", 0.5),
            ("Tomatoes", 0.6),
            ("Cucumber", 0.6),
            ("Bell Pepper", 0.4),
            ("Olive Oil", 0.3),
            ("Lemons", 0.4),
            ("Chicken Breast", 0.4),
        ],
    ),
    "stir_fry": (
        0.8,
        [
            ("Jasmine Rice", 0.8),
            ("Soy Sauce", 0.7),
            ("Broccoli", 0.6),
            ("Chicken Breast", 0.6),
            ("Bell Pepper", 0.5),
            ("Garlic", 0.5),
            ("Shrimp", 0.3),
            ("Mushrooms", 0.3),
            ("Carrots", 0.4),
        ],
    ),
    "cookout": (
        0.7,
        [
            ("Hamburger Buns", 0.8),
            ("Ground Beef", 0.6),
            ("Hot Dogs", 0.5),
            ("Ketchup", 0.6),
            ("Mustard", 0.5),
            ("Cola", 0.4),
            ("Potato Chips", 0.5),
            ("Lager Beer", 0.4),
            ("Lemonade", 0.2),
        ],
    ),
    "healthy_breakfast": (
        0.9,
        [
            ("Greek Yogurt", 0.8),
            ("Granola", 0.7),
            ("Blueberries", 0.5),
            ("Strawberries", 0.5),
            ("Bananas", 0.5),
            ("Oat Milk", 0.3),
            ("Oatmeal", 0.3),
        ],
    ),
    "movie_night": (
        0.7,
        [
            ("Popcorn", 0.7),
            ("Dark Chocolate", 0.5),
            ("Cola", 0.5),
            ("Frozen Pizza", 0.5),
            ("Vanilla Ice Cream", 0.5),
            ("Potato Chips", 0.4),
        ],
    ),
    "mezze": (
        0.5,
        [
            ("Hummus", 0.9),
            ("Pita Chips", 0.7),
            ("Cucumber", 0.5),
            ("Carrots", 0.5),
            ("Sparkling Water", 0.3),
        ],
    ),
    "salmon_dinner": (
        0.6,
        [
            ("Salmon Fillet", 0.9),
            ("Lemons", 0.7),
            ("Jasmine Rice", 0.4),
            ("Baby Spinach", 0.4),
            ("Garlic", 0.4),
            ("Butter", 0.3),
            ("Red Wine", 0.2),
        ],
    ),
    "caprese": (
        0.4,
        [
            ("Fresh Mozzarella", 0.9),
            ("Tomatoes", 0.8),
            ("Olive Oil", 0.5),
            ("Sourdough Bread", 0.3),
        ],
    ),
    "brunch": (
        0.5,
        [
            ("Bagels", 0.8),
            ("Croissants", 0.4),
            ("Orange Juice", 0.5),
            ("Coffee Beans", 0.4),
            ("Heavy Cream", 0.3),
        ],
    ),
    "comfort_dinner": (
        0.6,
        [
            ("Potatoes", 0.8),
            ("Butter", 0.5),
            ("Heavy Cream", 0.4),
            ("Chicken Breast", 0.5),
            ("Carrots", 0.4),
            ("Yellow Onion", 0.5),
            ("Frozen Peas", 0.4),
            ("Garlic", 0.3),
        ],
    ),
    "kids_lunch": (
        0.6,
        [
            ("Peanut Butter", 0.8),
            ("Strawberry Jam", 0.7),
            ("Sourdough Bread", 0.5),
            ("Apples", 0.6),
            ("Whole Milk", 0.4),
            ("Bananas", 0.4),
        ],
    ),
    "household": (
        0.5,
        [("Paper Towels", 0.7), ("Dish Soap", 0.6), ("Trash Bags", 0.6), ("Sparkling Water", 0.3)],
    ),
}

STAPLES: list[tuple[str, float]] = [
    ("Bananas", 0.30),
    ("Whole Milk", 0.25),
    ("Large Eggs", 0.20),
    ("Apples", 0.10),
]


def generate_baskets(n_orders: int, seed: int = 42) -> list[list[str]]:
    """Synthetic baskets of product names. Deterministic for a given seed."""
    rng = random.Random(seed)
    names = [p[0] for p in CATALOG]
    mission_names = list(MISSIONS)
    weights = [MISSIONS[m][0] for m in mission_names]

    baskets: list[list[str]] = []
    for _ in range(n_orders):
        basket: set[str] = set()
        n_missions = rng.choice([1, 1, 1, 2, 2, 3])
        for mission in rng.choices(mission_names, weights=weights, k=n_missions):
            items = MISSIONS[mission][1]
            picked = [name for name, p in items if rng.random() < p]
            basket.update(picked or [items[0][0]])
        basket.update(name for name, p in STAPLES if rng.random() < p)
        basket.update(rng.sample(names, k=rng.randint(0, 2)))  # impulse buys / noise
        baskets.append(sorted(basket))
    return baskets


def instacart_available() -> bool:
    return (INSTACART_DIR / "products.csv").exists() and (INSTACART_DIR / "orders.csv.gz").exists()


def read_instacart_orders(max_orders: int = 0) -> list[tuple[int, list[int]]]:
    """(user_id, product_ids) per order, in file order (by user, then order number).

    ``max_orders`` > 0 keeps only the first N orders, i.e. the complete histories of the
    first users in the file.
    """
    orders: dict[int, tuple[int, list[int]]] = {}
    with gzip.open(INSTACART_DIR / "orders.csv.gz", "rt", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            order_id = int(row["order_id"])
            if order_id not in orders:
                if max_orders and len(orders) >= max_orders:
                    break
                orders[order_id] = (int(row["user_id"]), [])
            orders[order_id][1].append(int(row["product_id"]))
    return list(orders.values())


def _seed_instacart(db: Session, max_orders: int) -> int:
    with open(INSTACART_DIR / "products.csv", newline="", encoding="utf-8") as f:
        products = [
            {
                "id": int(r["id"]),  # keep Instacart product ids so they match the raw dataset
                "name": r["name"],
                "department": r["department"],
                "aisle": r["aisle"],
                "price_cents": int(r["price_cents"]),
                "emoji": r["emoji"],
                "image_url": r.get("image_url") or None,
                "popularity": int(r.get("popularity") or 0),
            }
            for r in csv.DictReader(f)
        ]
    db.execute(insert(Product), products)

    orders = read_instacart_orders(max_orders)
    db.execute(insert(Order), [{"id": i, "user_id": u} for i, (u, _) in enumerate(orders, 1)])
    db.execute(
        insert(OrderItem),
        [{"order_id": i, "product_id": p} for i, (_, items) in enumerate(orders, 1) for p in items],
    )

    # Explicit ids bypass Postgres sequences; move them past the seeded rows so checkout works.
    if db.get_bind().dialect.name == "postgresql":
        for table in ("products", "orders"):
            seq = f"pg_get_serial_sequence('{table}', 'id')"
            db.execute(text(f"SELECT setval({seq}, MAX(id)) FROM {table}"))
    return len(orders)


def _seed_synthetic(db: Session, n_orders: int) -> int:
    products = [
        Product(name=n, department=d, aisle=a, price_cents=c, emoji=e) for n, d, a, c, e in CATALOG
    ]
    db.add_all(products)
    db.flush()
    ids = {p.name: p.id for p in products}

    for basket in generate_baskets(n_orders):
        db.add(Order(items=[OrderItem(product_id=ids[name]) for name in basket]))
    return n_orders


def seed_if_empty(db: Session, source: str = "instacart", n_orders: int = 0) -> str | None:
    """Seed catalog and order history if the products table is empty.

    Returns a description of what was seeded, or None if the DB already had data.
    Falls back to synthetic data when the Instacart files are missing.
    """
    if db.scalar(select(Product.id).limit(1)) is not None:
        return None

    if source == "instacart" and instacart_available():
        seeded = _seed_instacart(db, n_orders)
        what = f"Instacart catalog and {seeded} real orders"
    else:
        seeded = _seed_synthetic(db, n_orders or SYNTHETIC_DEFAULT_ORDERS)
        what = f"synthetic catalog and {seeded} generated orders"
        if source == "instacart":
            what += f" (no Instacart data in {INSTACART_DIR})"
    db.commit()
    return what
