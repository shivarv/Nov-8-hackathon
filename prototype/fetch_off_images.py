"""Find product photos on Open Food Facts for the most popular Instacart products.

Open Food Facts allows about 10 searches a minute, so this is slow (about 6 per
minute here) and resumable: products already tried are skipped on a re-run.

A photo is kept only when the Open Food Facts product name (with its brand)
contains most of the words of the Instacart name. Images are CC BY-SA, credited
by the product page link stored next to them.

Run from the repo root:
    prototype/.venv/bin/python prototype/fetch_off_images.py --top 600
"""

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prototype" / "out" / "off_images.csv"
DB = ROOT / "backend" / "instacart.db"
USER_AGENT = "GroceryHackathonPrototype/0.1 (hackathon demo)"
SEARCH = "https://world.openfoodfacts.org/cgi/search.pl"
DELAY_S = 10.0
MIN_SCORE = 0.5
STOP = {"of", "the", "and", "with", "in", "a", "&", "oz", "fl", "lb", "ct", "pack"}


def tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP and not t.isdigit()}


def search(name: str) -> list[dict]:
    params = {
        "search_terms": name,
        "search_simple": 1,
        "json": 1,
        "page_size": 8,
        "fields": "code,product_name,brands,image_front_url,image_front_small_url",
        "tagtype_0": "countries",
        "tag_contains_0": "contains",
        "tag_0": "united-states",
    }
    req = urllib.request.Request(
        f"{SEARCH}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp).get("products", [])


def best_match(name: str, products: list[dict]) -> tuple[float, dict] | None:
    want = tokens(name)
    best = None
    for p in products:
        if not p.get("image_front_url"):
            continue
        have = tokens(f"{p.get('product_name', '')} {p.get('brands', '')}")
        score = len(want & have) / max(len(want | have), 1)  # Jaccard: the names must mostly agree
        if best is None or score > best[0]:
            best = (score, p)
    return best if best and best[0] >= MIN_SCORE else None


def main() -> None:
    import sqlite3

    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=600, help="how many popular products to try")
    args = ap.parse_args()

    products = sqlite3.connect(DB).execute(
        "select id, name from products order by popularity desc, id limit ?", (args.top,)
    ).fetchall()
    done = set()
    if OUT.exists():
        done = {r["product_id"] for r in csv.DictReader(open(OUT))}
    else:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "w", newline="") as f:
            csv.writer(f).writerow(["product_id", "image_url", "credit_url", "off_name", "score"])

    todo = [(pid, name) for pid, name in products if str(pid) not in done]
    print(f"{len(done)} already tried, {len(todo)} to go (about {len(todo) * DELAY_S / 60:.0f} min)")
    found = 0
    for i, (pid, name) in enumerate(todo, 1):
        for attempt in range(3):
            try:
                match = best_match(name, search(name))
                break
            except Exception as e:  # rate limit or network: back off and retry
                print(f"  retry {attempt + 1} for {name!r}: {e}", flush=True)
                time.sleep(DELAY_S * (attempt + 2))
        else:
            continue  # leave untried so a re-run picks it up
        with open(OUT, "a", newline="") as f:
            w = csv.writer(f)
            if match:
                score, p = match
                found += 1
                w.writerow([
                    pid,
                    p["image_front_url"],
                    f"https://world.openfoodfacts.org/product/{p['code']}",
                    f"{p.get('product_name', '')} ({p.get('brands', '')})",
                    f"{score:.2f}",
                ])
            else:
                w.writerow([pid, "", "", "", ""])  # tried, no good match
        if i % 25 == 0:
            print(f"  {i}/{len(todo)} tried, {found} photos found", flush=True)
        time.sleep(DELAY_S)
    print(f"done: {found} photos found in {len(todo)} products tried")


if __name__ == "__main__":
    main()
