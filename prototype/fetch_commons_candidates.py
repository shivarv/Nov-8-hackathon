"""Find grocery-style photo candidates on Wikimedia Commons and lay them out for a visual pick.

Wikipedia's main article photo often shows the plant (spinach in a field), not the
food as you'd buy it. This searches Commons with store-style wording per food
("baby spinach leaves", "carton of eggs"), keeps up to 9 usable photos, and draws
them on one numbered contact sheet per food so a person or model can pick the one
that looks like a grocery item.

Input:  prototype/image_sources/commons_queries.csv   title|query1|query2|query3
Output: prototype/out/commons/candidates.json         title -> [candidate, ...]
        prototype/out/commons/sheets/NNN.jpg          one 3x3 sheet per title
        prototype/out/commons/sheets/index.txt        NNN|title|number of candidates

Picks go in prototype/image_sources/commons_picks.csv (title|choice, 0 = none fit),
which build_images.py reads. Re-running skips titles already fetched.

Run from the repo root:
    prototype/.venv/bin/python prototype/fetch_commons_candidates.py
"""

import io
import json
import sys
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
QUERIES = ROOT / "prototype" / "image_sources" / "commons_queries.csv"
OUT = ROOT / "prototype" / "out" / "commons"
SHEETS = OUT / "sheets"
THUMBS = OUT / "thumbs"
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "GroceryHackathonPrototype/0.1 (https://github.com/shivarv/Nov-8-hackathon; hackathon demo)"
SHEET_WIDTH = 330  # a standard Wikimedia thumbnail width, cached by their CDN
APP_WIDTH = 500  # what the app shows; also a standard width
PER_SHEET = 9
CELL = 260

# Filenames with these words are almost never a food as sold in a store.
_REJECT = {
    "map", "diagram", "drawing", "illustration", "logo", "herbarium", "botanical",
    "flower", "flowers", "flowering", "bloeiend", "field", "fields", "farm", "farming",
    "garden", "plantation", "seedling", "seedlings", "nursery", "tree", "trees",
    "recalled", "icon", "chart", "stamp", "poster", "advert", "advertisement",
    "factory", "museum", "label", "sign", "cartoon", "painting", "engraving", "plate",
    "distribution", "range", "worms", "insect", "pest", "disease", "leaf spot",
}


def _get(url: str, attempts: int = 6) -> bytes:
    """GET with back-off on 429 / 5xx, honouring Retry-After."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == attempts - 1:
                raise
            wait = float(e.headers.get("Retry-After") or 0) or 3 * 2**attempt
            print(f"  HTTP {e.code}, waiting {min(wait, 60):.0f}s", flush=True)
            time.sleep(min(wait, 60))
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
            time.sleep(3 * 2**attempt)
    raise RuntimeError("unreachable")


def search(query: str) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "generator": "search",
        "gsrnamespace": 6,
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrlimit": 15,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": SHEET_WIDTH,
        "iiextmetadatafilter": "LicenseShortName|Artist",
    }
    data = json.loads(_get(f"{API}?{urllib.parse.urlencode(params)}"))
    pages = sorted(data.get("query", {}).get("pages", []), key=lambda p: p["index"])
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if "thumburl" not in ii:
            continue
        meta = ii.get("extmetadata", {})
        out.append(
            {
                "file": p["title"],
                "width": ii["width"],
                "height": ii["height"],
                "sheet_url": ii["thumburl"],
                "original_url": ii["url"],
                "credit_url": ii["descriptionurl"],
                "license": meta.get("LicenseShortName", {}).get("value", ""),
            }
        )
    return out


def usable(c: dict) -> bool:
    words = set(re.findall(r"[a-z]+", c["file"].lower()))
    if words & _REJECT:
        return False
    w, h = c["width"], c["height"]
    return min(w, h) >= 500 and 0.5 <= w / h <= 2.0 and bool(c["license"])


def app_url(c: dict) -> str:
    """Same thumbnail at the width the app shows, or the original when it is smaller."""
    if c["width"] <= APP_WIDTH:
        return c["original_url"]
    return re.sub(r"/\d+px-", f"/{APP_WIDTH}px-", c["sheet_url"])


def candidates_for(queries: list[str]) -> list[dict]:
    """Round-robin over the queries so each wording contributes its best hits."""
    results = []
    for q in queries:
        results.append([c for c in search(q) if usable(c)])
        time.sleep(0.3)
    seen, picked = set(), []
    for rank in range(max((len(r) for r in results), default=0)):
        for r in results:
            if rank < len(r) and r[rank]["file"] not in seen:
                seen.add(r[rank]["file"])
                picked.append(r[rank])
    return picked[:PER_SHEET]


def thumb(c: dict) -> Image.Image | None:
    path = THUMBS / (re.sub(r"[^A-Za-z0-9]+", "_", c["file"])[:120] + ".jpg")
    if not path.exists():
        try:
            img = Image.open(io.BytesIO(_get(c["sheet_url"]))).convert("RGB")
        except Exception:
            return None
        img.save(path, quality=80)
    try:
        img = Image.open(path)
        img.load()
        return img
    except Exception:  # a half-written file from an interrupted run
        return None


def font(size: int) -> ImageFont.ImageFont:
    for name in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sheet(title: str, cands: list[dict], pool: ThreadPoolExecutor) -> Image.Image:
    head = 44
    img = Image.new("RGB", (CELL * 3, head + CELL * 3), "white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 8), title, fill="black", font=font(26))
    for i, t in enumerate(pool.map(thumb, cands)):
        x, y = (i % 3) * CELL, head + (i // 3) * CELL
        if t is not None:
            t.thumbnail((CELL - 8, CELL - 8))
            img.paste(t, (x + (CELL - t.width) // 2, y + (CELL - t.height) // 2))
        draw.rectangle((x + 4, y + 4, x + 44, y + 44), fill="#ffd84d")
        draw.text((x + 14, y + 6), str(i + 1), fill="black", font=font(30))
    return img


def main() -> None:
    global QUERIES, OUT, SHEETS, THUMBS
    priority_only = "--priority-only" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) > 1:  # optional: queries file and output folder, for trial runs
        QUERIES, OUT = Path(args[0]), Path(args[1])
        SHEETS, THUMBS = OUT / "sheets", OUT / "thumbs"
    SHEETS.mkdir(parents=True, exist_ok=True)
    THUMBS.mkdir(parents=True, exist_ok=True)
    cand_path = OUT / "candidates.json"
    cands: dict[str, list[dict]] = json.loads(cand_path.read_text()) if cand_path.exists() else {}
    rows = [line.rstrip("\n").split("|") for line in open(QUERIES) if line.strip()]

    # Titles listed in priority.txt (e.g. the demo shoppers' foods) are fetched first;
    # with --priority-only, only those. Commons throttles, so this gets the photos
    # that will be seen fixed soonest.
    pri_path = OUT / "priority.txt"
    priority = pri_path.read_text().split("\n") if pri_path.exists() else []
    rank = {t: i for i, t in enumerate(t for t in priority if t)}
    todo = sorted(
        (r for r in rows if r[0] not in cands and (r[0] in rank or not priority_only)),
        key=lambda r: rank.get(r[0], len(rank)),
    )
    for n, (title, *queries) in enumerate(todo, 1):
        cands[title] = candidates_for([q for q in queries if q.strip()])
        for c in cands[title]:
            c["app_url"] = app_url(c)
        print(f"[{n}/{len(todo)}] {title}: {len(cands[title])} candidates", flush=True)
        cand_path.write_text(json.dumps(cands, indent=1))

    index = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for n, (title, *_q) in enumerate(rows, 1):
            if title not in cands:
                continue
            path = SHEETS / f"{n:03d}.jpg"
            if cands[title] and not path.exists():
                sheet(title, cands[title], pool).save(path, quality=70)
            index.append(f"{n:03d}|{title}|{len(cands[title])}")
            if n % 50 == 0:
                print(f"sheets: {n}/{len(rows)}", flush=True)
    (SHEETS / "index.txt").write_text("\n".join(index) + "\n")
    print(f"done: {sum(1 for c in cands.values() if c)}/{len(rows)} titles have candidates")


if __name__ == "__main__":
    main()
