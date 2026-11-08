import logging

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.deps import BehaviorGPT, DbSession, Recommender
from app.models import Cart, Product
from app.recommender import CoOccurrenceRecommender, Recommendation
from app.schemas import ProductOut, RecommendationOut

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
log = logging.getLogger("uvicorn.error")

# BehaviorGPT candidates fetched per suggestion shown, and the minimum number of
# purchases a product needs in the loaded orders to be suggested.
CANDIDATE_FACTOR = 5
MIN_POPULARITY = 20


def _hydrate(db: DbSession, recs: list[Recommendation]) -> list[RecommendationOut]:
    ids = {r.product_id for r in recs} | {r.because_product_id for r in recs}
    ids.discard(None)
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}

    out = []
    for r in recs:
        product = products.get(r.product_id)
        if product is None:  # model knows an id the catalog no longer has
            continue
        because = products.get(r.because_product_id) if r.because_product_id else None
        if r.source == "behaviorgpt":
            reason = "Goes with your basket"
        elif because:
            reason = f"Often bought with {because.name}"
        else:
            reason = "Popular right now"
        out.append(
            RecommendationOut(
                product=ProductOut.model_validate(product),
                score=r.score,
                source=r.source,
                reason=reason,
            )
        )
    return out


def _recommend(
    db: DbSession,
    product_ids: list[int],
    k: int,
    recommender: CoOccurrenceRecommender,
    bgpt: BehaviorGPT,
) -> list[Recommendation]:
    """BehaviorGPT when it is configured and the basket has items, else bought-together.

    BehaviorGPT ranks the whole catalog, including products almost nobody buys
    (in the Instacart data, 10k products were never bought in the loaded orders),
    and those make odd suggestions. So we ask it for more candidates than needed
    and keep, in its order, only products bought at least `MIN_POPULARITY` times.
    """
    if bgpt is not None and product_ids:
        try:
            candidates = bgpt.goes_with(product_ids, k * CANDIDATE_FACTOR)
            popularity = dict(
                db.execute(
                    select(Product.id, Product.popularity).where(
                        Product.id.in_([pid for pid, _ in candidates])
                    )
                ).all()
            )
            kept = [(pid, s) for pid, s in candidates if popularity.get(pid, 0) >= MIN_POPULARITY]
            if kept:
                return [Recommendation(pid, round(s, 4), "behaviorgpt") for pid, s in kept[:k]]
            log.warning("BehaviorGPT returned only rarely bought products; using bought-together")
        except Exception:  # network, quota, bad key: keep the shop working
            log.exception("BehaviorGPT call failed; falling back to bought-together")
    return recommender.recommend(product_ids, k=k)


@router.get("/cart/{cart_id}", response_model=list[RecommendationOut])
def recommend_for_cart(
    cart_id: str,
    db: DbSession,
    recommender: Recommender,
    bgpt: BehaviorGPT,
    k: int = Query(8, ge=1, le=50),
):
    """'Complete your cart' – items that pair with everything currently in the cart."""
    cart = db.get(Cart, cart_id)
    if cart is None:
        raise HTTPException(404, "Cart not found")
    product_ids = [ci.product_id for ci in cart.items]
    return _hydrate(db, _recommend(db, product_ids, k, recommender, bgpt))


@router.get("/product/{product_id}", response_model=list[RecommendationOut])
def recommend_for_product(
    product_id: int,
    db: DbSession,
    recommender: Recommender,
    bgpt: BehaviorGPT,
    k: int = Query(6, ge=1, le=50),
):
    """'Frequently bought together' for a single product."""
    if db.get(Product, product_id) is None:
        raise HTTPException(404, "Product not found")
    return _hydrate(db, _recommend(db, [product_id], k, recommender, bgpt))
