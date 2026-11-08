"""Build the BehaviorGPT catalog file from the Instacart products.

Writes prototype/out/instacart_products.parquet (the file name becomes the
catalog's name on Unbox AI). Run from the repo root:

    prototype/.venv/bin/python prototype/build_catalog.py
"""

import csv
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from behaviorgpt.resources.catalogs import CATALOG_SCHEMA, check_catalog_schema

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
OUT = ROOT / "prototype" / "out" / "instacart_products.parquet"


def read(name: str) -> list[dict[str, str]]:
    with open(ARCHIVE / name, newline="") as f:
        return list(csv.DictReader(f))


def purchase_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    with open(ARCHIVE / "order_products__prior.csv") as f:
        next(f)
        for line in f:
            counts[line.split(",", 2)[1]] += 1
    return counts


def main() -> None:
    aisles = {r["aisle_id"]: r["aisle"] for r in read("aisles.csv")}
    departments = {r["department_id"]: r["department"] for r in read("departments.csv")}
    with open(ROOT / "data" / "product_prices.csv", newline="") as f:
        prices = {r["product_id"]: r["price_usd"] for r in csv.DictReader(f)}
    counts = purchase_counts()

    rows: dict[str, list] = {name: [] for name in CATALOG_SCHEMA}
    for p in read("products.csv"):
        pid = p["product_id"]
        n = counts.get(pid, 0)
        rows["id"].append(pid)
        rows["name"].append(p["product_name"])
        rows["brand"].append(None)  # Instacart has no brand column
        rows["categories"].append(f"{departments[p['department_id']]}, {aisles[p['aisle_id']]}")
        rows["image_url"].append(None)  # text-only embedding
        rows["event_type"].append("product")
        rows["group"].append("product")
        # Instacart has no dates, so spread each product's purchases evenly over a year:
        # trailing 30, 60, ..., 330 days, then the all-time total.
        rows["sales_since"].append([round(n * k / 12) for k in range(1, 12)] + [n])
        rows["timestamp"].append(None)
        rows["frequency"].append(n)
        rows["market"].append("US")
        rows["price"].append(prices.get(pid))
        rows["currency"].append("USD")
        rows["search_keywords"].append(None)
        rows["keywords"].append(None)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pydict(rows, schema=pa.schema(CATALOG_SCHEMA))
    pq.write_table(table, OUT)
    check_catalog_schema(OUT)
    print(f"wrote {table.num_rows} items to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
