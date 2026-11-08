from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.deps import DbSession
from app.models import Product
from app.schemas import ProductOut

router = APIRouter(tags=["products"])


@router.get("/products", response_model=list[ProductOut])
def list_products(
    db: DbSession,
    q: str | None = None,
    department: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    stmt = select(Product).order_by(Product.popularity.desc(), Product.name).limit(limit)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    if department:
        stmt = stmt.where(Product.department == department)
    return db.scalars(stmt).all()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: DbSession):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/departments", response_model=list[str])
def list_departments(db: DbSession):
    return db.scalars(select(Product.department).distinct().order_by(Product.department)).all()
