from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.deps import DbSession, Recommender
from app.models import Cart, Product
from app.recommender import Recommendation
from app.schemas import ProductOut, RecommendationOut

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


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
        reason = f"Often bought with {because.name}" if because else "Popular right now"
        out.append(
            RecommendationOut(
                product=ProductOut.model_validate(product),
                score=r.score,
                source=r.source,
                reason=reason,
            )
        )
    return out


@router.get("/cart/{cart_id}", response_model=list[RecommendationOut])
def recommend_for_cart(
    cart_id: str, db: DbSession, recommender: Recommender, k: int = Query(8, ge=1, le=50)
):
    """'Complete your cart' – items that pair with everything currently in the cart."""
    cart = db.get(Cart, cart_id)
    if cart is None:
        raise HTTPException(404, "Cart not found")
    recs = recommender.recommend([ci.product_id for ci in cart.items], k=k)
    return _hydrate(db, recs)


@router.get("/product/{product_id}", response_model=list[RecommendationOut])
def recommend_for_product(
    product_id: int,
    db: DbSession,
    recommender: Recommender,
    k: int = Query(6, ge=1, le=50),
):
    """'Frequently bought together' for a single product."""
    if db.get(Product, product_id) is None:
        raise HTTPException(404, "Product not found")
    return _hydrate(db, recommender.recommend([product_id], k=k))
