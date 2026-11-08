import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import behaviorgpt, images, instacart, newusers, seedfile, shoppers
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import OrderItem, Product
from app.recommender import CoOccurrenceRecommender
from app.routers import carts, feed, products, recommendations
from app.seed import seed_if_empty

log = logging.getLogger("uvicorn.error")


def seed_database(db: Session) -> str | None:
    """Fill an empty DB from Instacart or synthetic data. Returns what was loaded, or None."""
    if db.scalar(select(Product.id).limit(1)) is not None:
        return None
    if settings.data_source != "synthetic" and seedfile.available(settings.seed_file):
        # The pre-built seed (deployments): the same catalog and orders, ~1 MB.
        n = seedfile.load(db, settings.seed_file)
        return f"Loaded the Instacart catalog and {n} real orders from {settings.seed_file}"
    has_instacart = instacart.available(settings.instacart_dir, settings.prices_csv)
    if settings.data_source == "instacart" and not has_instacart:
        raise RuntimeError(
            f"DATA_SOURCE=instacart but neither the seed ({settings.seed_file}) nor the "
            f"dataset was found (INSTACART_DIR={settings.instacart_dir}, "
            f"PRICES_CSV={settings.prices_csv})"
        )
    if settings.data_source == "instacart" or (settings.data_source == "auto" and has_instacart):
        n = instacart.load(
            db, settings.instacart_dir, settings.prices_csv, settings.instacart_orders
        )
        return f"Loaded the Instacart catalog and {n} real orders"
    seed_if_empty(db, settings.seed_orders)
    return f"Seeded catalog and {settings.seed_orders} synthetic orders"


def build_recommender(db: Session) -> CoOccurrenceRecommender:
    baskets: defaultdict[int, list[int]] = defaultdict(list)
    for order_id, product_id in db.execute(select(OrderItem.order_id, OrderItem.product_id)):
        baskets[order_id].append(product_id)
    return CoOccurrenceRecommender().fit(baskets.values())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hackathon-grade schema management; switch to Alembic once the schema settles.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if loaded := seed_database(db):
            log.info(loaded)
        app.state.recommender = build_recommender(db)
    log.info("Recommender trained on %d baskets", app.state.recommender.n_baskets)
    app.state.behaviorgpt = behaviorgpt.make(settings.unboxai_api_key, settings.unboxai_catalog_id)
    n_products, n_aisles = images.load(settings.product_images_csv, settings.aisle_images_csv)
    log.info("Photos for %d products and %d aisles", n_products, n_aisles)
    log.info("%d demo shoppers", shoppers.load(settings.demo_shoppers_json))
    with SessionLocal() as db:
        log.info("%d new shoppers", newusers.load_all(db))
    yield


app = FastAPI(title="Better Basket API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (products.router, carts.router, recommendations.router, feed.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "baskets": app.state.recommender.n_baskets,
        "behaviorgpt": app.state.behaviorgpt is not None,
    }


# --- the built frontend (deployment: one service serves the app and its API) ----------
# FRONTEND_DIST points at `npm run build` output (the root Dockerfile sets it). Locally
# it's unset and Vite serves the frontend, proxying /api here.
if settings.frontend_dist and Path(settings.frontend_dist, "index.html").is_file():
    dist = Path(settings.frontend_dist).resolve()
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        """Files from the build (favicon...), else index.html: the app routes itself."""
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist):
            return FileResponse(file)
        return FileResponse(dist / "index.html")
