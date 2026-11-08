"""Combine product photos from Open Food Facts and Wikipedia into the app's image files.

Inputs (prototype/image_sources/):
  product_wiki.csv  product_id|kind|wiki_title   for the 2,000 most-bought products
  aisle_wiki.csv    aisle|wiki_title             for all 134 aisles
  commons_picks.csv title|image_url|credit_url|alt_image_url|alt_credit_url
                    grocery-style photos picked by eye (fetch_commons_candidates.py,
                    then apply_commons_picks.py), if present
  plus prototype/out/off_images.csv from fetch_off_images.py, if it has run.

Outputs (data/), read by the backend:
  product_images.csv  product_id,image_url,source,credit_url
  aisle_images.csv    aisle,image_url,credit_url

A product gets, in order: its Open Food Facts photo (exact product), else the
picked Commons photo of its kind of food (alternating with the second pick, so
products of the same kind don't all share one photo), else the main photo of its
Wikipedia article. The app shows the aisle
photo for every other product. Wikipedia photos are requested with
pilicense=free, so only freely licensed images are used.

Run from the repo root:
    prototype/.venv/bin/python prototype/build_images.py
"""

import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "prototype" / "image_sources"
OFF = ROOT / "prototype" / "out" / "off_images.csv"
DATA = ROOT / "data"
USER_AGENT = "GroceryHackathonPrototype/0.1 (hackathon demo)"
API = "https://en.wikipedia.org/w/api.php"

# Second-choice articles, tried when the first one has no freely licensed main photo.
FALLBACK_TITLES = {
    "Black bean": "Black turtle bean",
    "Bouillon": "Bouillon cube",
    "Cold brew": "Cold brew coffee",
    "Cracker": "Cracker (food)",
    "Creamer": "Non-dairy creamer",
    "Crescent roll": "Croissant",
    "Dip": "French onion dip",
    "Gala": "Gala (apple)",
    "Honeydew": "Honeydew (melon)",
    "Lime": "Persian lime",
    "Mint": "Mentha",
    "Pickle": "Pickled cucumber",
    "Plantain": "Cooking banana",
    "Popsicle": "Ice pop",
    "Sage": "Salvia officinalis",
    "Swiss cheese": "Swiss cheese (North America)",
}


def wiki_images(titles: set[str]) -> dict[str, tuple[str, str]]:
    """title -> (thumbnail url, file page url), for titles whose article has a free main image."""
    out: dict[str, tuple[str, str]] = {}
    titles_list = sorted(titles)
    for i in range(0, len(titles_list), 50):
        batch = titles_list[i : i + 50]
        params = {
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "prop": "pageimages",
            "piprop": "thumbnail|name",
            "pithumbsize": 400,
            "pilicense": "free",
            "redirects": 1,
            "titles": "|".join(batch),
        }
        req = urllib.request.Request(
            f"{API}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT}
        )
        q = _get_json(req)["query"]
        # Map each requested title through normalization and redirects to its page.
        alias = {t: t for t in batch}
        for step in ("normalized", "redirects"):
            for m in q.get(step, []):
                for k, v in alias.items():
                    if v == m["from"]:
                        alias[k] = m["to"]
        pages = {p["title"]: p for p in q.get("pages", [])}
        for requested, final in alias.items():
            p = pages.get(final)
            if p and "thumbnail" in p:
                file_page = "https://en.wikipedia.org/wiki/File:" + urllib.parse.quote(
                    p["pageimage"].replace(" ", "_")
                )
                out[requested] = (p["thumbnail"]["source"], file_page)
        time.sleep(2.0)
    return out


def _get_json(req: urllib.request.Request, attempts: int = 6) -> dict:
    """GET with back-off on 429 / 5xx, honouring Retry-After when Wikipedia sends it."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == attempts - 1:
                raise
            wait = float(e.headers.get("Retry-After") or 0) or 5 * 2**attempt
            print(f"  HTTP {e.code}, waiting {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("unreachable")


_STOP = {"of", "the", "and", "with", "in", "a", "&", "oz", "fl", "lb", "ct", "pack"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _STOP and not t.isdigit()}


def same_product(instacart_name: str, off_name: str) -> bool:
    """Names share most of their words (Jaccard >= 0.5), not just one containing the other."""
    a, b = _tokens(instacart_name), _tokens(off_name)
    return len(a & b) / max(len(a | b), 1) >= 0.5


def read_pipe(path: Path) -> list[list[str]]:
    with open(path) as f:
        next(f)
        return [line.rstrip("\n").split("|") for line in f if line.strip()]


def main() -> None:
    product_src = SRC / "product_wiki.csv"
    products = read_pipe(product_src) if product_src.exists() else []
    aisles = read_pipe(SRC / "aisle_wiki.csv")
    titles = {t for _, _, t in products} | {t for _, t in aisles}
    images = wiki_images(titles | {FALLBACK_TITLES[t] for t in titles if t in FALLBACK_TITLES})
    for first, second in FALLBACK_TITLES.items():
        if first not in images and second in images:
            images[first] = images[second]

    names = {
        r["product_id"]: r["product_name"]
        for r in csv.DictReader(open(ROOT / "archive" / "products.csv"))
    }
    # Package photos only for packaged products, and only when the names really agree;
    # fresh food (bananas, zucchini) always gets the photo of the food itself.
    packaged = {pid for pid, kind, _ in products if kind == "packaged"}
    off = {}
    if OFF.exists():
        off = {
            r["product_id"]: r
            for r in csv.DictReader(open(OFF))
            if r["image_url"]
            and r["product_id"] in packaged
            and same_product(names[r["product_id"]], r["off_name"])
        }

    picks: dict[str, list[tuple[str, str]]] = {}
    picks_src = SRC / "commons_picks.csv"
    if picks_src.exists():
        for title, url, credit, alt_url, alt_credit in read_pipe(picks_src):
            picks[title] = [(url, credit)] + ([(alt_url, alt_credit)] if alt_url else [])
    seen_title: dict[str, int] = {}

    counts = {"openfoodfacts": 0, "commons": 0, "wikipedia": 0, "none": 0}
    with open(DATA / "product_images.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["product_id", "image_url", "source", "credit_url"])
        for pid, _kind, title in products:
            if pid in off:
                w.writerow([pid, off[pid]["image_url"], "openfoodfacts", off[pid]["credit_url"]])
                counts["openfoodfacts"] += 1
            elif title in picks:
                n = seen_title.get(title, 0)
                seen_title[title] = n + 1
                url, credit = picks[title][n % len(picks[title])]
                w.writerow([pid, url, "commons", credit])
                counts["commons"] += 1
            elif title in images:
                url, credit = images[title]
                w.writerow([pid, url, "wikipedia", credit])
                counts["wikipedia"] += 1
            else:
                counts["none"] += 1

    missing_aisles = []
    with open(DATA / "aisle_images.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["aisle", "image_url", "credit_url"])
        for aisle, title in aisles:
            if title in picks:
                w.writerow([aisle, *picks[title][0]])
            elif title in images:
                w.writerow([aisle, *images[title]])
            else:
                missing_aisles.append(f"{aisle} ({title})")

    print(f"products: {counts}")
    print(f"aisles: {len(aisles) - len(missing_aisles)}/{len(aisles)} with a photo")
    if missing_aisles:
        print("  no free photo for:", "; ".join(missing_aisles))


if __name__ == "__main__":
    main()
