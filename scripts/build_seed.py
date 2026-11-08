"""Build data/seed.json.xz: the Instacart catalog and order sample the app loads, ~1 MB.

Loads the raw dataset (archive/) with the backend's own loader into a scratch
database, then writes it out compactly (backend/app/seedfile.py). Deployments load
this file instead of the raw dataset, with the same result.

    backend/.venv/bin/python scripts/build_seed.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import instacart, seedfile  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base  # noqa: E402

OUT = ROOT / "data" / "seed.json.xz"


def main() -> None:
    archive, prices = ROOT / "archive", ROOT / "data" / "product_prices.csv"
    if not instacart.available(str(archive), str(prices)):
        sys.exit("archive/ not found: download the Instacart dataset first (data/README.md)")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    t = time.time()
    with Session(engine) as db:
        instacart.load(db, str(archive), str(prices), settings.instacart_orders)
        counts = seedfile.dump(db, str(OUT))
    print(
        f"{OUT.relative_to(ROOT)}: {counts['products']} products, {counts['orders']} orders, "
        f"{OUT.stat().st_size / 1e6:.2f} MB ({time.time() - t:.0f}s)"
    )


if __name__ == "__main__":
    main()
