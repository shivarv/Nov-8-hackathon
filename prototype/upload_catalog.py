"""Upload (or refresh) the Instacart catalog on Unbox AI and save its id.

Uploading the same file name again refreshes the same catalog. Run from the repo root:

    prototype/.venv/bin/python prototype/upload_catalog.py
"""

from datetime import UTC, datetime
from pathlib import Path

from behaviorgpt import UnboxAIClient
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PARQUET = ROOT / "prototype" / "out" / "instacart_products.parquet"
ID_FILE = ROOT / "prototype" / "catalog_id.txt"

load_dotenv(ROOT / ".env")


def main() -> None:
    client = UnboxAIClient(market="US", timezone="America/New_York")
    job = client.embed(
        PARQUET,
        wait=True,
        timeout=3600.0,
        reference_time=datetime.now(tz=UTC),
        on_progress=lambda s: print(f"  {s.status}", flush=True),
    )
    ID_FILE.write_text(job.catalog_id + "\n")
    print(f"catalog ready: {job.catalog_id} (saved to {ID_FILE.relative_to(ROOT)})")


if __name__ == "__main__":
    main()
