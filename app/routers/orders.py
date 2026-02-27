from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import InventoryMovement, Order, OrderItem, Product
from ..schemas import CheckoutRequest, CheckoutResponse, OrderItemOut, OrderSummaryOut
from ..services.bookkeeping import record_double_entry
from ..utils import to_money

router = APIRouter(tags=["orders"])


@router.get("/orders", response_model=list[OrderSummaryOut])
def list_orders(
    limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)
) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("/checkout", response_model=CheckoutResponse, status_code=201)
def checkout(payload: CheckoutRequest, db: Session = Depends(get_db)) -> CheckoutResponse:
    requested_qty: dict[int, int] = {}
    for item in payload.items:
        requested_qty[item.product_id] = requested_qty.get(item.product_id, 0) + item.quantity

    product_ids = list(requested_qty.keys())
    stmt = select(Product).where(Product.id.in_(product_ids), Product.is_active.is_(True))
    products = list(db.scalars(stmt).all())
    product_map = {p.id: p for p in products}

    missing_ids = [pid for pid in product_ids if pid not in product_map]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Produk tidak ditemukan atau tidak aktif: {missing_ids}",
        )

    for product_id, qty in requested_qty.items():
        product = product_map[product_id]
        if product.stock_qty < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Stok tidak cukup untuk {product.name}. Tersedia {product.stock_qty}, diminta {qty}.",
            )

    subtotal = Decimal("0.00")
    cogs = Decimal("0.00")
    lines: list[tuple[Product, int, Decimal, Decimal, Decimal, Decimal]] = []

    for product_id, qty in requested_qty.items():
        product = product_map[product_id]
        unit_price = to_money(product.sell_price)
        unit_cost = to_money(product.cost_price)
        line_total = to_money(unit_price * qty)
        line_cost = to_money(unit_cost * qty)
        subtotal += line_total
        cogs += line_cost
        lines.append((product, qty, unit_price, unit_cost, line_total, line_cost))

    subtotal = to_money(subtotal)
    discount = to_money(payload.discount)
    tax = to_money(payload.tax)
    total = to_money(subtotal - discount + tax)
    cogs = to_money(cogs)

    if total < 0:
        raise HTTPException(status_code=400, detail="Total transaksi tidak valid.")

    order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')}"
    order = Order(
        order_number=order_number,
        payment_method=payload.payment_method,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=total,
    )
    db.add(order)
    db.flush()

    response_items: list[OrderItemOut] = []
    for product, qty, unit_price, unit_cost, line_total, line_cost in lines:
        before_qty = product.stock_qty
        after_qty = before_qty - qty
        product.stock_qty = after_qty

        db.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=qty,
                unit_price=unit_price,
                cost_price=unit_cost,
                line_total=line_total,
                line_cost_total=line_cost,
            )
        )
        db.add(
            InventoryMovement(
                product_id=product.id,
                movement_type="sale",
                quantity_change=-qty,
                before_qty=before_qty,
                after_qty=after_qty,
                reason=f"Checkout {order_number}",
                ref_type="order",
                ref_id=order.id,
            )
        )
        response_items.append(
            OrderItemOut(
                product_id=product.id,
                product_name=product.name,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    receipt_account = "Accounts Receivable" if payload.payment_method == "credit" else "Cash"
    note = f"Checkout order {order_number}"
    record_double_entry(db, order_number, receipt_account, "Sales Revenue", total, note)
    record_double_entry(db, order_number, "COGS", "Inventory", cogs, note)

    db.commit()
    db.refresh(order)

    gross_profit = to_money(total - cogs)
    return CheckoutResponse(
        order_id=order.id,
        order_number=order.order_number,
        created_at=order.created_at,
        payment_method=order.payment_method,
        subtotal=order.subtotal,
        discount=order.discount,
        tax=order.tax,
        total=order.total,
        cogs=cogs,
        gross_profit=gross_profit,
        items=response_items,
    )
