"""Turn the visual picks into prototype/image_sources/commons_picks.csv for build_images.py.

Input:  prototype/out/commons/picks.txt   NNN|best|second   (sheet numbers 1-9, 0 = none)
        prototype/out/commons/sheets/index.txt and candidates.json from fetch_commons_candidates.py
Output: prototype/image_sources/commons_picks.csv
        title|image_url|credit_url|alt_image_url|alt_credit_url

Run from the repo root:
    prototype/.venv/bin/python prototype/apply_commons_picks.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prototype" / "out" / "commons"
DEST = ROOT / "prototype" / "image_sources" / "commons_picks.csv"


def main() -> None:
    cands = json.loads((OUT / "candidates.json").read_text())
    titles = {}
    for line in (OUT / "sheets" / "index.txt").read_text().splitlines():
        n, title, _count = line.split("|")
        titles[n] = title

    rows, none = [], []
    for line in (OUT / "picks.txt").read_text().splitlines():
        if not line.strip():
            continue
        n, best, second = (line.split("|") + ["0", "0"])[:3]
        title = titles[n.zfill(3)]
        options = cands[title]

        def pick(k: str) -> dict | None:
            i = int(k or 0)
            return options[i - 1] if 1 <= i <= len(options) else None

        a, b = pick(best), pick(second)
        if a is None:
            none.append(title)
            continue
        b = b if b and b["app_url"] != a["app_url"] else None
        rows.append(
            [title, a["app_url"], a["credit_url"], b["app_url"] if b else "", b["credit_url"] if b else ""]
        )

    with open(DEST, "w") as f:
        f.write("title|image_url|credit_url|alt_image_url|alt_credit_url\n")
        for r in sorted(rows):
            f.write("|".join(r) + "\n")
    print(f"{len(rows)} foods with a picked photo; no good photo for {len(none)}")
    if none:
        print("  keeping the old photo for:", "; ".join(none))


if __name__ == "__main__":
    main()
