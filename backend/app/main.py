import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import behaviorgpt, images, instacart, shoppers
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
    has_instacart = instacart.available(settings.instacart_dir, settings.prices_csv)
    if settings.data_source == "instacart" and not has_instacart:
        raise RuntimeError(
            f"DATA_SOURCE=instacart but the dataset was not found "
            f"(INSTACART_DIR={settings.instacart_dir}, PRICES_CSV={settings.prices_csv})"
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
    yield


app = FastAPI(title="Grocery Recommender API", lifespan=lifespan)
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
