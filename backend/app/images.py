"""Product photos: the product's own photo, else its aisle's photo, else none (emoji).

Read once at startup from data/product_images.csv and data/aisle_images.csv
(built by prototype/build_images.py). Either file may be missing.
"""

import csv
from pathlib import Path

_product: dict[int, str] = {}
_aisle: dict[str, str] = {}


def load(product_csv: str, aisle_csv: str) -> tuple[int, int]:
    _product.clear()
    _aisle.clear()
    if Path(product_csv).is_file():
        with open(product_csv, newline="") as f:
            _product.update({int(r["product_id"]): r["image_url"] for r in csv.DictReader(f)})
    if Path(aisle_csv).is_file():
        with open(aisle_csv, newline="") as f:
            _aisle.update({r["aisle"]: r["image_url"] for r in csv.DictReader(f)})
    return len(_product), len(_aisle)


def image_for(product_id: int, aisle: str) -> str | None:
    return _product.get(product_id) or _aisle.get(aisle)
