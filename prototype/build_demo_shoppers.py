"""Pick a few contrasting real Instacart shoppers for the app's "Who's shopping?" screen.

Reads the 300-shopper sample (prototype/out/shoppers_sample.json, made by
explore.py) and writes data/demo_shoppers.json with each chosen shopper's past
orders (items in the order they were added) and a short description computed
from those orders. The held-out next order is left out.

Run from the repo root:
    prototype/.venv/bin/python prototype/build_demo_shoppers.py
"""

import csv
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "prototype" / "out" / "shoppers_sample.json"
OUT = ROOT / "data" / "demo_shoppers.json"
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def part_of_day(hour: int) -> str:
    if hour < 12:
        return "mornings"
    if hour < 17:
        return "afternoons"
    return "evenings"


def main() -> None:
    sample = json.loads(SAMPLE.read_text())
    products = {r["product_id"]: r for r in csv.DictReader(open(ROOT / "archive" / "products.csv"))}
    departments = {
        r["department_id"]: r["department"]
        for r in csv.DictReader(open(ROOT / "archive" / "departments.csv"))
    }
    prices = {
        r["product_id"]: float(r["price_usd"])
        for r in csv.DictReader(open(ROOT / "data" / "product_prices.csv"))
    }
    by_aisle: dict[str, list[float]] = {}
    for pid, p in products.items():
        by_aisle.setdefault(p["aisle_id"], []).append(prices[pid])
    aisle_median = {a: statistics.median(v) for a, v in by_aisle.items()}

    stats = []
    for uid, orders in sample.items():
        past = [o for o in orders if not o["held_out"]]
        items = [pid for o in past for pid in o["items"]]
        if len(past) < 10 or not items:
            continue
        organic = sum("organic" in products[p]["product_name"].lower() for p in items) / len(items)
        price_idx = statistics.fmean(prices[p] / aisle_median[products[p]["aisle_id"]] for p in items)
        basket = statistics.fmean(len(o["items"]) for o in past)
        dow = Counter(o["dow"] for o in past).most_common(1)[0][0]
        hour = round(statistics.median(o["hour"] for o in past))
        top_dept = Counter(departments[products[p]["department_id"]] for p in items).most_common(1)[0][0]
        stats.append(
            dict(id=uid, past=past, organic=organic, price_idx=price_idx, basket=basket,
                 dow=dow, hour=hour, top_dept=top_dept)
        )

    # One shopper per persona, each the most extreme example of it.
    personas = [
        ("Mostly organic", lambda s: s["organic"]),
        ("Budget-minded", lambda s: -s["price_idx"]),
        ("Big weekly shop", lambda s: s["basket"]),
        ("Quick top-ups", lambda s: -s["basket"]),
        ("Pricier picks", lambda s: s["price_idx"] - s["organic"]),
        ("Steady regular", lambda s: len(s["past"])),
    ]
    chosen, used = [], set()
    for label, key in personas:
        s = max((s for s in stats if s["id"] not in used), key=key)
        used.add(s["id"])
        chosen.append(
            {
                "id": int(s["id"]),
                "label": label,
                "blurb": (
                    f"{round(s['basket'])} items a trip, usually {DAYS[s['dow']]} "
                    f"{part_of_day(s['hour'])} · {round(100 * s['organic'])}% organic"
                ),
                "usual_day": DAYS[s["dow"]],
                "usual_hour": s["hour"],
                "orders": [{"dow": o["dow"], "hour": o["hour"], "items": [int(p) for p in o["items"]]} for o in s["past"]],
            }
        )
        print(f"{label:<22} shopper {s['id']:>6}: {chosen[-1]['blurb']}")

    OUT.write_text(json.dumps(chosen))
    print(f"wrote {len(chosen)} shoppers to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
