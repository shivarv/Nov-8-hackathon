"""Build the backend's seed dataset from the raw Instacart CSVs.

Reads   archive/*.csv            (Kaggle "Instacart Online Grocery Basket Analysis", not in git)
        data/product_prices.csv  (estimated prices, in git)
Writes  backend/data/instacart/products.csv
        backend/data/instacart/orders.csv.gz

The catalog is the N most-purchased products. Orders are the complete histories of a
random sample of real users, restricted to catalog products. Deterministic for a given seed.

    pip install pandas
    python scripts/build_instacart_seed.py [--products 3000] [--users 4000] [--seed 42]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
OUT = ROOT / "backend" / "data" / "instacart"

DEPARTMENT_NAMES = {
    "dairy eggs": "Dairy & Eggs",
    "meat seafood": "Meat & Seafood",
    "dry goods pasta": "Dry Goods & Pasta",
    "missing": "Other",
}

# Checked in order against the lowercased product name; first match wins.
NAME_EMOJI: list[tuple[str, str]] = [
    ("banana", "🍌"), ("strawberr", "🍓"), ("blueberr", "🫐"), ("raspberr", "🫐"),
    ("blackberr", "🫐"), ("avocado", "🥑"), ("lemon", "🍋"), ("lime", "🍋"),
    ("watermelon", "🍉"), ("melon", "🍈"), ("cantaloupe", "🍈"), ("honeydew", "🍈"),
    ("grape", "🍇"), ("pineapple", "🍍"),
    ("mango", "🥭"), ("peach", "🍑"), ("nectarine", "🍑"), ("cherr", "🍒"), ("pear", "🍐"),
    ("orange", "🍊"), ("clementine", "🍊"), ("mandarin", "🍊"), ("kiwi", "🥝"),
    ("coconut", "🥥"), ("apple", "🍎"), ("tomato", "🍅"), ("potato", "🥔"),
    ("carrot", "🥕"), ("broccoli", "🥦"), ("cucumber", "🥒"), ("zucchini", "🥒"),
    ("pepper", "🫑"), ("jalapeno", "🌶️"), ("onion", "🧅"), ("garlic", "🧄"),
    ("mushroom", "🍄"), ("corn", "🌽"), ("spinach", "🥬"), ("lettuce", "🥬"),
    ("kale", "🥬"), ("romaine", "🥬"), ("cilantro", "🌿"), ("parsley", "🌿"),
    ("basil", "🌿"), ("egg", "🥚"), ("milk", "🥛"), ("butter", "🧈"), ("cheese", "🧀"),
    ("yogurt", "🥣"), ("bread", "🍞"), ("bagel", "🥯"), ("croissant", "🥐"),
    ("tortilla", "🫓"), ("bacon", "🥓"), ("chicken", "🍗"), ("turkey", "🦃"),
    ("beef", "🥩"), ("steak", "🥩"), ("salmon", "🐟"), ("shrimp", "🦐"),
    ("hot dog", "🌭"), ("sausage", "🌭"), ("pizza", "🍕"), ("pasta", "🍝"),
    ("spaghetti", "🍝"), ("rice", "🍚"), ("honey", "🍯"), ("peanut", "🥜"),
    ("chocolate", "🍫"), ("cookie", "🍪"), ("ice cream", "🍨"), ("popcorn", "🍿"),
    ("coffee", "☕"), ("tea", "🍵"), ("water", "💧"), ("juice", "🧃"), ("soda", "🥤"),
    ("beer", "🍺"), ("wine", "🍷"),
]

AISLE_EMOJI: dict[str, str] = {
    "fresh fruits": "🍎", "fresh vegetables": "🥦", "fresh herbs": "🌿",
    "packaged vegetables fruits": "🥗", "packaged produce": "🥗", "milk": "🥛",
    "soy lactosefree": "🥛", "eggs": "🥚", "butter": "🧈", "packaged cheese": "🧀",
    "specialty cheeses": "🧀", "other creams cheeses": "🧀", "cream": "🥛", "yogurt": "🥣",
    "bread": "🍞", "breakfast bakery": "🥐", "buns rolls": "🍔", "tortillas flat bread": "🫓",
    "bakery desserts": "🍰", "cookies cakes": "🍪", "crackers": "🍘",
    "chips pretzels": "🥨", "popcorn jerky": "🍿", "candy chocolate": "🍫",
    "nuts seeds dried fruit": "🥜", "trail mix snack mix": "🥜", "energy granola bars": "🍫",
    "fruit vegetable snacks": "🍎", "mint gum": "🍬", "cereal": "🥣", "granola": "🥣",
    "hot cereal pancake mixes": "🥞", "breakfast bars pastries": "🥐", "coffee": "☕",
    "tea": "🍵", "water seltzer sparkling water": "💧", "soft drinks": "🥤",
    "juice nectars": "🧃", "energy sports drinks": "🥤", "cocoa drink mixes": "☕",
    "beers coolers": "🍺", "red wines": "🍷", "white wines": "🥂",
    "specialty wines champagnes": "🍾", "spirits": "🥃", "frozen pizza": "🍕",
    "ice cream ice": "🍨", "frozen dessert": "🍨", "frozen produce": "🧊",
    "frozen meals": "🍱", "frozen breakfast": "🧇", "frozen appetizers sides": "🍟",
    "frozen meat seafood": "🧊", "frozen vegan vegetarian": "🥦", "frozen breads doughs": "🍞",
    "frozen juice": "🧃", "dry pasta": "🍝", "fresh pasta": "🍝", "pasta sauce": "🥫",
    "grains rice dried goods": "🍚", "bulk grains rice dried goods": "🍚",
    "canned meals beans": "🥫", "canned jarred vegetables": "🥫",
    "canned fruit applesauce": "🥫", "canned meat seafood": "🐟", "soup broth bouillon": "🍲",
    "instant foods": "🍜", "asian foods": "🥢", "latino foods": "🌮", "indian foods": "🍛",
    "kosher foods": "🥯", "condiments": "🍅", "salad dressing toppings": "🥗",
    "spreads": "🥜", "preserved dips spreads": "🫙", "fresh dips tapenades": "🫙",
    "pickled goods olives": "🫒", "oils vinegars": "🫒", "spices seasonings": "🧂",
    "baking ingredients": "🌾", "baking supplies decor": "🧁",
    "doughs gelatins bake mixes": "🧁", "honeys syrups nectars": "🍯",
    "marinades meat preparation": "🧂", "packaged meat": "🥩", "meat counter": "🥩",
    "packaged poultry": "🍗", "poultry counter": "🍗", "hot dogs bacon sausage": "🌭",
    "lunch meat": "🥪", "packaged seafood": "🐟", "seafood counter": "🐟",
    "tofu meat alternatives": "🌱", "prepared soups salads": "🥗", "prepared meals": "🍱",
    "refrigerated": "🧊", "refrigerated pudding desserts": "🍮",
    "protein meal replacements": "💪", "paper goods": "🧻", "trash bags liners": "🗑️",
    "dish detergents": "🧼", "laundry": "🧺", "cleaning products": "🧽",
    "food storage": "📦", "kitchen supplies": "🍳", "plates bowls cups flatware": "🍽️",
    "air fresheners candles": "🕯️", "more household": "🏠", "soap": "🧼",
    "body lotions soap": "🧴", "skin care": "🧴", "facial care": "🧴", "hair care": "🧴",
    "oral hygiene": "🪥", "deodorants": "🧴", "shave needs": "🪒", "feminine care": "🌸",
    "beauty": "💄", "vitamins supplements": "💊", "cold flu allergy": "💊",
    "digestion": "💊", "muscles joints pain relief": "💊", "first aid": "🩹",
    "eye ear care": "💧", "diapers wipes": "🍼", "baby food formula": "🍼",
    "baby bath body care": "🍼", "baby accessories": "🍼", "dog food care": "🐕",
    "cat food care": "🐈", "ice cream toppings": "🍒",
}


# Name keywords only for produce; elsewhere ("Chicken & Apple Sausage") the aisle is more accurate.
NAME_EMOJI_DEPARTMENTS = {"produce"}
_NAME_PATTERNS = [(re.compile(rf"\b{re.escape(w)}"), e) for w, e in NAME_EMOJI]


def emoji_for(name: str, aisle: str, department: str) -> str:
    if department in NAME_EMOJI_DEPARTMENTS:
        lower = name.lower()
        for pattern, emoji in _NAME_PATTERNS:
            if pattern.search(lower):
                return emoji
    return AISLE_EMOJI.get(aisle, "🛒")


def build_products(n_products: int) -> pd.DataFrame:
    prior = pd.read_csv(
        ARCHIVE / "order_products__prior.csv", usecols=["product_id"], dtype="int32"
    )
    counts = prior.product_id.value_counts().head(n_products).rename("popularity")

    products = pd.read_csv(ARCHIVE / "products.csv")
    aisles = pd.read_csv(ARCHIVE / "aisles.csv")
    departments = pd.read_csv(ARCHIVE / "departments.csv")
    prices = pd.read_csv(ROOT / "data" / "product_prices.csv")

    df = (
        products.merge(counts, left_on="product_id", right_index=True)
        .merge(aisles, on="aisle_id")
        .merge(departments, on="department_id")
        .merge(prices[["product_id", "price_usd"]], on="product_id")
    )
    if len(df) != n_products:
        raise SystemExit(f"expected {n_products} products after joins, got {len(df)}")

    # Photos from scripts/fetch_product_images.py, where one was found. Open Food Facts photos
    # are shopper-taken: loose produce comes out as blurry shelf shots (the emoji looks better),
    # and one-word names ("Soda") match the wrong product too often.
    images_file = ROOT / "data" / "product_images.csv"
    if images_file.exists():
        images = pd.read_csv(images_file, usecols=["product_id", "image_url"])
        df = df.merge(images, on="product_id", how="left")
        unreliable = (df.department == "produce") | (df.product_name.str.split().str.len() < 2)
        df.loc[unreliable, "image_url"] = None
    else:
        df["image_url"] = None

    return pd.DataFrame(
        {
            "id": df.product_id,
            "name": df.product_name.str.strip(),
            "department": df.department.map(lambda d: DEPARTMENT_NAMES.get(d, d.title())),
            "aisle": df.aisle.str.title(),
            "price_cents": (df.price_usd * 100).round().astype(int),
            "emoji": [
                emoji_for(n, a, d)
                for n, a, d in zip(df.product_name, df.aisle, df.department, strict=True)
            ],
            "image_url": df.image_url,
            "popularity": df.popularity,
        }
    ).sort_values("id")


def build_orders(product_ids: set[int], n_users: int, seed: int) -> pd.DataFrame:
    orders = pd.read_csv(ARCHIVE / "orders.csv")
    orders = orders[orders.eval_set != "test"]  # test orders have no products
    users = orders.user_id.drop_duplicates().sample(n=n_users, random_state=seed)
    orders = orders[orders.user_id.isin(users)]

    lines = pd.concat(
        pd.read_csv(ARCHIVE / f, dtype="int32")
        for f in ("order_products__prior.csv", "order_products__train.csv")
    )
    lines = lines[lines.order_id.isin(orders.order_id) & lines.product_id.isin(product_ids)]

    df = orders.merge(lines, on="order_id")
    df["days_since_prior_order"] = df.days_since_prior_order.astype("Int64")
    return df.sort_values(["user_id", "order_number", "add_to_cart_order"])[
        [
            "order_id", "user_id", "eval_set", "order_number", "order_dow",
            "order_hour_of_day", "days_since_prior_order", "product_id",
            "add_to_cart_order", "reordered",
        ]
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--products", type=int, default=3000, help="catalog size (top-N by purchases)")
    ap.add_argument("--users", type=int, default=4000, help="users whose order history is kept")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    products = build_products(args.products)
    products.to_csv(OUT / "products.csv", index=False)

    orders = build_orders(set(products.id), args.users, args.seed)
    orders.to_csv(OUT / "orders.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})

    n_orders = orders.order_id.nunique()
    print(f"products: {len(products)}  ->  {OUT / 'products.csv'}")
    print(
        f"orders:   {n_orders} from {orders.user_id.nunique()} users, {len(orders)} lines, "
        f"{len(orders) / n_orders:.1f} items/order  ->  {OUT / 'orders.csv.gz'}"
    )


if __name__ == "__main__":
    main()
