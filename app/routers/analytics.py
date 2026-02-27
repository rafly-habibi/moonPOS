from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Order, OrderItem, Product
from ..schemas import SalesSummaryOut, StockValuationOut, TopProductOut
from ..utils import day_end, day_start, to_money

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/sales-summary", response_model=SalesSummaryOut)
def sales_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> SalesSummaryOut:
    filters = []
    if start_date:
        filters.append(Order.created_at >= day_start(start_date))
    if end_date:
        filters.append(Order.created_at <= day_end(end_date))

    order_stmt = select(
        func.count(Order.id),
        func.coalesce(func.sum(Order.subtotal), 0),
        func.coalesce(func.sum(Order.discount), 0),
        func.coalesce(func.sum(Order.tax), 0),
        func.coalesce(func.sum(Order.total), 0),
    )
    if filters:
        order_stmt = order_stmt.where(*filters)
    order_count, subtotal, discount, tax, revenue = db.execute(order_stmt).one()

    item_stmt = select(
        func.coalesce(func.sum(OrderItem.quantity), 0),
        func.coalesce(func.sum(OrderItem.line_cost_total), 0),
    ).join(Order, Order.id == OrderItem.order_id)
    if filters:
        item_stmt = item_stmt.where(*filters)
    items_sold, cogs = db.execute(item_stmt).one()

    revenue_value = to_money(revenue)
    cogs_value = to_money(cogs)
    return SalesSummaryOut(
        order_count=order_count,
        subtotal=to_money(subtotal),
        discount=to_money(discount),
        tax=to_money(tax),
        revenue=revenue_value,
        items_sold=int(items_sold or 0),
        cogs=cogs_value,
        gross_profit=to_money(revenue_value - cogs_value),
        avg_order_value=to_money(revenue_value / order_count) if order_count else Decimal("0.00"),
    )


@router.get("/top-products", response_model=list[TopProductOut])
def top_products(
    limit: int = Query(10, ge=1, le=100),
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> list[TopProductOut]:
    filters = []
    if start_date:
        filters.append(Order.created_at >= day_start(start_date))
    if end_date:
        filters.append(Order.created_at <= day_end(end_date))

    qty_expr = func.coalesce(func.sum(OrderItem.quantity), 0).label("qty_sold")
    revenue_expr = func.coalesce(func.sum(OrderItem.line_total), 0).label("revenue")

    stmt = (
        select(Product.id, Product.name, qty_expr, revenue_expr)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
    )
    if filters:
        stmt = stmt.where(*filters)
    stmt = (
        stmt.group_by(Product.id, Product.name)
        .order_by(desc(qty_expr), desc(revenue_expr))
        .limit(limit)
    )

    return [
        TopProductOut(
            product_id=pid,
            product_name=name,
            qty_sold=int(qty_sold or 0),
            revenue=to_money(revenue),
        )
        for pid, name, qty_sold, revenue in db.execute(stmt).all()
    ]


@router.get("/stock-valuation", response_model=StockValuationOut)
def stock_valuation(db: Session = Depends(get_db)) -> StockValuationOut:
    products = list(db.scalars(select(Product).where(Product.is_active.is_(True))).all())
    total_units = sum(p.stock_qty for p in products)
    cost_value = Decimal("0.00")
    retail_value = Decimal("0.00")
    for p in products:
        cost_value += to_money(p.cost_price) * p.stock_qty
        retail_value += to_money(p.sell_price) * p.stock_qty
    cost_value = to_money(cost_value)
    retail_value = to_money(retail_value)
    return StockValuationOut(
        active_products=len(products),
        total_units=total_units,
        inventory_cost_value=cost_value,
        inventory_retail_value=retail_value,
        potential_margin=to_money(retail_value - cost_value),
    )
