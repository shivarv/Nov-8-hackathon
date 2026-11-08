import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.models import OrderItem
from app.recommender import CoOccurrenceRecommender
from app.routers import carts, products, recommendations
from app.seed import seed_if_empty

log = logging.getLogger("uvicorn.error")


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
        if seeded := seed_if_empty(db, settings.seed_source, settings.seed_orders):
            log.info("Seeded %s", seeded)
        app.state.recommender = build_recommender(db)
    log.info("Recommender trained on %d baskets", app.state.recommender.n_baskets)
    yield


app = FastAPI(title="Grocery Recommender API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (products.router, carts.router, recommendations.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "baskets": app.state.recommender.n_baskets}
