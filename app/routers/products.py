from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Product
from ..schemas import ProductCreate, ProductOut

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    product = Product(**payload.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU sudah dipakai.") from exc
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductOut])
def list_products(
    low_stock_only: bool = Query(False),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[Product]:
    stmt = select(Product)
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if low_stock_only:
        stmt = stmt.where(Product.stock_qty <= Product.min_stock)
    stmt = stmt.order_by(Product.name.asc())
    return list(db.scalars(stmt).all())
