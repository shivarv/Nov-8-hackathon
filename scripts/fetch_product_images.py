"""Find a product photo for each catalog product on Open Food Facts.

Reads   backend/data/instacart/products.csv
Writes  data/product_images.csv  (product_id, image_url, off_code, off_name, score)

For each product, searches Open Food Facts (https://world.openfoodfacts.org) by name and
keeps the best hit whose name closely matches ours and that has a front photo. Products
without a confident match are left out; the UI falls back to the emoji for those.
Photos are CC BY-SA (Open Food Facts contributors) and are linked, not copied.

Resumable: products already in the output file are skipped, so it can be re-run after an
interruption. Standard library only (uses certifi for HTTPS certificates if installed).

    python scripts/fetch_product_images.py [--limit N] [--min-score 0.75]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:  # python.org builds on macOS ship without system CA certificates
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

ROOT = Path(__file__).resolve().parent.parent
PRODUCTS = ROOT / "backend" / "data" / "instacart" / "products.csv"
OUT = ROOT / "data" / "product_images.csv"
SEARCH = "https://search.openfoodfacts.org/search"
USER_AGENT = "basket-hackathon-demo/0.1 (Instacart catalog image matching)"
FIELDS = ["product_id", "image_url", "off_code", "off_name", "score"]

STOPWORDS = {"of", "the", "and", "with", "a", "in", "&", "bag", "each", "ct", "oz", "pack"}


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w.rstrip("s") if len(w) > 3 else w for w in words if w not in STOPWORDS}


def match_score(ours: str, theirs: str) -> float:
    """Share of our name's words found in theirs, penalised if theirs has many extra words."""
    a, b = tokens(ours), tokens(theirs)
    if not a or not b:
        return 0.0
    common = len(a & b)
    return min(common / len(a), 2 * common / len(b))


def search(name: str) -> list[dict]:
    params = {
        "q": name,
        "page_size": "10",
        "fields": "code,product_name,image_front_small_url,image_front_url",
    }
    req = urllib.request.Request(
        f"{SEARCH}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
                return json.load(resp).get("hits", [])
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
        except (TimeoutError, ConnectionError):
            pass
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLError):
                raise  # certificate problems won't fix themselves; fail loudly
        time.sleep(5 * (attempt + 1))  # rate limit or network hiccup: back off and retry
    return []


def best_image(name: str, min_score: float) -> dict | None:
    best = None
    for hit in search(name):
        url = hit.get("image_front_url") or hit.get("image_front_small_url")
        off_name = hit.get("product_name") or ""
        if not url or not off_name:
            continue
        score = match_score(name, off_name)
        if score >= min_score and (best is None or score > best["score"]):
            best = {"image_url": url, "off_code": hit.get("code", ""), "off_name": off_name,
                    "score": round(score, 2)}
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=0, help="only look up the first N products")
    ap.add_argument("--min-score", type=float, default=0.75)
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    args = ap.parse_args()

    with open(PRODUCTS, newline="", encoding="utf-8") as f:
        products = list(csv.DictReader(f))
    if args.limit:
        products = products[: args.limit]

    done: set[str] = set()
    if OUT.exists():
        with open(OUT, newline="", encoding="utf-8") as f:
            done = {r["product_id"] for r in csv.DictReader(f)}
    # Products looked up with no match are remembered too, so re-runs skip them.
    misses_file = OUT.with_suffix(".misses")
    if misses_file.exists():
        done |= set(misses_file.read_text().split())

    new_file = not OUT.exists()
    with open(OUT, "a", newline="", encoding="utf-8") as out, open(misses_file, "a") as misses:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        todo = [p for p in products if p["id"] not in done]
        found = 0
        for n, p in enumerate(todo, 1):
            hit = best_image(p["name"], args.min_score)
            if hit:
                writer.writerow({"product_id": p["id"], **hit})
                found += 1
            else:
                misses.write(p["id"] + "\n")
            out.flush()
            misses.flush()
            if n % 50 == 0 or n == len(todo):
                print(f"{n}/{len(todo)} looked up, {found} images found", flush=True)
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
