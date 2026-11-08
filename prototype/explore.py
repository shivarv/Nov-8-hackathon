"""Replay real Instacart shoppers through BehaviorGPT and see what it suggests.

For each shopper:
  1. History = their previous orders (each one a cart session ending in an order).
  2. "Your usuals": what BehaviorGPT suggests before they add anything.
  3. Then their real next order (held out by Instacart, never shown to the model)
     is added item by item, in the order they really added things. After each
     add, BehaviorGPT re-ranks "what else goes in this basket".
  Every suggestion is marked [x] if the shopper really bought it in that order.

A simple baseline is shown next to it: the shopper's own most-bought items.

Run from the repo root:
    prototype/.venv/bin/python prototype/explore.py              # 3 random shoppers
    prototype/.venv/bin/python prototype/explore.py --users 5 --seed 4
    prototype/.venv/bin/python prototype/explore.py --user-id 1
"""

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

from behaviorgpt import Order, UnboxAIClient, View
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
CACHE = ROOT / "prototype" / "out" / "shoppers_sample.json"
CATALOG_ID_FILE = ROOT / "prototype" / "catalog_id.txt"
CATALOG_ID = CATALOG_ID_FILE.read_text().strip() if CATALOG_ID_FILE.exists() else None

load_dotenv(ROOT / ".env")

SAMPLE_SIZE = 300  # shoppers kept in the local cache
MIN_ORDERS, MAX_ORDERS = 8, 40


# ---------- data ----------------------------------------------------------


def build_cache(seed: int = 7) -> dict:
    """Sample shoppers who have a held-out last order and cache their orders (slow, once)."""
    print("Building shopper cache from the Instacart files (about a minute, only once)...")
    orders = list(csv.DictReader(open(ARCHIVE / "orders.csv")))
    n_orders = Counter(o["user_id"] for o in orders)
    eligible = sorted(
        {o["user_id"] for o in orders if o["eval_set"] == "train"}
        & {u for u, n in n_orders.items() if MIN_ORDERS <= n <= MAX_ORDERS},
        key=int,
    )
    users = set(random.Random(seed).sample(eligible, SAMPLE_SIZE))

    meta = {}
    for o in orders:
        if o["user_id"] in users and o["eval_set"] in ("prior", "train"):
            meta[o["order_id"]] = o
    items: dict[str, list[tuple[int, str]]] = {oid: [] for oid in meta}
    for name in ("order_products__prior.csv", "order_products__train.csv"):
        with open(ARCHIVE / name) as f:
            next(f)
            for line in f:
                oid, pid, pos, _ = line.rstrip("\n").split(",")
                if oid in items:
                    items[oid].append((int(pos), pid))

    shoppers: dict[str, list] = {u: [] for u in users}
    for oid, o in meta.items():
        shoppers[o["user_id"]].append(
            {
                "order_number": int(o["order_number"]),
                "dow": int(o["order_dow"]),
                "hour": int(o["order_hour_of_day"]),
                "days_since_prior": o["days_since_prior_order"] or None,
                "held_out": o["eval_set"] == "train",
                "items": [pid for _, pid in sorted(items[oid])],
            }
        )
    for u in shoppers:
        shoppers[u].sort(key=lambda o: o["order_number"])
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(shoppers))
    return shoppers


def load_products() -> dict[str, dict]:
    aisles = {r["aisle_id"]: r["aisle"] for r in csv.DictReader(open(ARCHIVE / "aisles.csv"))}
    prices = {
        r["product_id"]: r["price_usd"]
        for r in csv.DictReader(open(ROOT / "data" / "product_prices.csv"))
    }
    return {
        r["product_id"]: {"name": r["product_name"], "aisle": aisles[r["aisle_id"]], "price": prices[r["product_id"]]}
        for r in csv.DictReader(open(ARCHIVE / "products.csv"))
    }


# ---------- model calls ---------------------------------------------------


def history_sessions(past_orders: list[dict], last_n: int) -> list[list]:
    """Each past order becomes one session: view items in the order they were added, then the order."""
    return [[View(pid) for pid in o["items"]] + [Order(o["items"])] for o in past_orders[-last_n:]]


def ranked_ids(client: UnboxAIClient, history: list, exclude: set[str], k: int, predict: str) -> list[str]:
    res = client.complete(history, limit=k + len(exclude), catalog_id=CATALOG_ID, predict=predict)
    return [it.id for it in res.items if it.id not in exclude][:k]


# ---------- output --------------------------------------------------------


def line(products: dict, pid: str, bought: set[str]) -> str:
    p = products[pid]
    mark = "[x]" if pid in bought else "[ ]"
    return f"      {mark} {p['name'][:46]:<46} ${p['price']:>6}  ({p['aisle']})"


def run_shopper(client, products, user_id: str, orders: list[dict], k: int, last_n: int, steps: int) -> dict:
    past = [o for o in orders if not o["held_out"]]
    target = next(o for o in orders if o["held_out"])
    basket = target["items"]
    bought = set(basket)
    days = DAYS[target["dow"]]

    print("=" * 96)
    print(f"Shopper {user_id}: {len(past)} past orders. Next order: {days} around {target['hour']}:00, "
          f"{target['days_since_prior'] or '?'} days after the previous one, {len(basket)} items.")
    print(f"Model sees the last {min(last_n, len(past))} orders. [x] = really in the next order.\n")

    history = history_sessions(past, last_n)

    # 1. Before anything is added
    usuals = ranked_ids(client, history, set(), k, "view")
    freq = [pid for pid, _ in Counter(pid for o in past for pid in o["items"]).most_common(k)]
    hits_model = sum(p in bought for p in usuals)
    hits_base = sum(p in bought for p in freq)
    print(f"  Session start: 'Your usuals' from BehaviorGPT ({hits_model}/{k} in the real basket)")
    for pid in usuals:
        print(line(products, pid, bought))
    print(f"  (Baseline, their {k} most-bought items: {hits_base}/{k} in the real basket)\n")

    # 2. Add the real basket item by item and re-rank after each add
    cart: list[str] = []
    step_hits = []
    for pid in basket[:steps]:
        cart.append(pid)
        session = [View(x) for x in cart]
        recs = ranked_ids(client, history + [session], set(cart), 5, "purchase")
        remaining = bought - set(cart)
        hits = sum(r in remaining for r in recs)
        step_hits.append((hits, len(remaining)))
        print(f"  + added {products[pid]['name'][:60]}   -> goes with your basket ({hits}/5 still to come)")
        for r in recs:
            print(line(products, r, remaining))
        if not remaining:
            break
    print()
    return {"usuals_hits": hits_model, "baseline_hits": hits_base, "basket": len(basket)}


DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]  # Instacart dow 0 = Sunday (assumed)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--users", type=int, default=3, help="how many random shoppers to replay")
    ap.add_argument("--user-id", help="replay this shopper (must be in the cached sample)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--k", type=int, default=10, help="how many 'usuals' to show")
    ap.add_argument("--last-orders", type=int, default=10, help="how many past orders the model sees")
    ap.add_argument("--steps", type=int, default=4, help="how many real items to add one by one")
    args = ap.parse_args()

    shoppers = json.loads(CACHE.read_text()) if CACHE.exists() else build_cache()
    products = load_products()
    client = UnboxAIClient(market="US", timezone="America/New_York")

    ids = [args.user_id] if args.user_id else random.Random(args.seed).sample(sorted(shoppers, key=int), args.users)
    results = [run_shopper(client, products, u, shoppers[u], args.k, args.last_orders, args.steps) for u in ids]

    if len(results) > 1:
        m = sum(r["usuals_hits"] for r in results)
        b = sum(r["baseline_hits"] for r in results)
        print(f"Summary over {len(results)} shoppers: 'Your usuals' hits {m}, most-bought baseline hits {b} "
              f"(out of {args.k * len(results)} suggestions each).")


if __name__ == "__main__":
    main()
