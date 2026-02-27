from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import InventoryMovement, Product
from ..schemas import InventoryAdjustmentRequest, InventoryMovementOut, ProductOut
from ..services.bookkeeping import record_double_entry
from ..utils import to_money

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/low-stock", response_model=list[ProductOut])
def low_stock_products(db: Session = Depends(get_db)) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True), Product.stock_qty <= Product.min_stock)
        .order_by(Product.stock_qty.asc(), Product.name.asc())
    )
    return list(db.scalars(stmt).all())


@router.get("/movements", response_model=list[InventoryMovementOut])
def list_inventory_movements(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[InventoryMovement]:
    stmt = (
        select(InventoryMovement)
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@router.post("/adjust", response_model=InventoryMovementOut)
def adjust_inventory(
    payload: InventoryAdjustmentRequest, db: Session = Depends(get_db)
) -> InventoryMovement:
    product = db.get(Product, payload.product_id)
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")

    before_qty = product.stock_qty
    after_qty = before_qty + payload.quantity_change
    if after_qty < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Stok tidak cukup. Stok saat ini {before_qty}, pengurangan {abs(payload.quantity_change)}.",
        )

    product.stock_qty = after_qty
    movement = InventoryMovement(
        product_id=product.id,
        movement_type="restock" if payload.quantity_change > 0 else "adjustment",
        quantity_change=payload.quantity_change,
        before_qty=before_qty,
        after_qty=after_qty,
        reason=payload.reason,
        ref_type="manual",
    )
    db.add(movement)

    tx_ref = f"INV-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    unit_cost = to_money(product.cost_price)
    value = to_money(unit_cost * abs(payload.quantity_change))
    counterparty = (
        payload.counterparty_account.strip()
        if payload.counterparty_account and payload.counterparty_account.strip()
        else ("Cash" if payload.quantity_change > 0 else "Inventory Shrinkage Expense")
    )
    note = payload.reason or f"Manual stock adjustment {product.sku}"

    if payload.quantity_change > 0:
        record_double_entry(db, tx_ref, "Inventory", counterparty, value, note)
    else:
        record_double_entry(db, tx_ref, counterparty, "Inventory", value, note)

    db.commit()
    db.refresh(movement)
    return movement
