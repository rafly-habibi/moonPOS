from __future__ import annotations

import os
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine, get_db
from .models import InventoryMovement, LedgerEntry, Order, OrderItem, Product
from .schemas import (
    CheckoutRequest,
    CheckoutResponse,
    InventoryAdjustmentRequest,
    InventoryMovementOut,
    LedgerEntryOut,
    OrderItemOut,
    OrderSummaryOut,
    ProductCreate,
    ProductOut,
    SalesSummaryOut,
    StockValuationOut,
    TopProductOut,
    TrialBalanceItem,
)

MONEY_STEP = Decimal("0.01")
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def to_money(value: Decimal | int | float | None) -> Decimal:
    if value is None:
        value = Decimal("0.00")
    return Decimal(str(value)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min)


def day_end(day: date) -> datetime:
    return datetime.combine(day, time.max)


def add_ledger_entry(
    db: Session,
    tx_ref: str,
    account: str,
    direction: str,
    amount: Decimal,
    note: str | None = None,
) -> None:
    if amount <= 0:
        return
    db.add(
        LedgerEntry(
            tx_ref=tx_ref,
            account=account,
            direction=direction,
            amount=to_money(amount),
            note=note,
        )
    )


def record_double_entry(
    db: Session,
    tx_ref: str,
    debit_account: str,
    credit_account: str,
    amount: Decimal,
    note: str | None,
) -> None:
    if amount <= 0:
        return
    add_ledger_entry(db, tx_ref, debit_account, "debit", amount, note)
    add_ledger_entry(db, tx_ref, credit_account, "credit", amount, note)


def seed_products(db: Session) -> None:
    count = db.scalar(select(func.count(Product.id))) or 0
    if count > 0:
        return

    db.add_all(
        [
            Product(
                sku="SKU-COF-01",
                name="Americano",
                category="Beverage",
                sell_price=Decimal("25000"),
                cost_price=Decimal("9000"),
                stock_qty=120,
                min_stock=20,
            ),
            Product(
                sku="SKU-COF-02",
                name="Cappuccino",
                category="Beverage",
                sell_price=Decimal("32000"),
                cost_price=Decimal("12000"),
                stock_qty=90,
                min_stock=15,
            ),
            Product(
                sku="SKU-FNB-01",
                name="Croissant",
                category="Food",
                sell_price=Decimal("18000"),
                cost_price=Decimal("7000"),
                stock_qty=70,
                min_stock=10,
            ),
        ]
    )
    db.commit()


app = FastAPI(
    title="moonPOS API",
    version="0.1.0",
    description="POS cloud-ready API untuk checkout, stok, pembukuan, dan analitik.",
)

cors_origins_raw = os.getenv("MOONPOS_CORS_ORIGINS", "*").strip()
allowed_origins = (
    ["*"]
    if cors_origins_raw == "*"
    else [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_products(db)


@app.get("/")
def root() -> dict[str, object]:
    return {"service": "moonPOS API", "status": "ok", "cloud_ready": True}


@app.get("/web", include_in_schema=False)
def web_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/products", response_model=ProductOut, status_code=201)
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


@app.get("/products", response_model=list[ProductOut])
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


@app.get("/inventory/low-stock", response_model=list[ProductOut])
def low_stock_products(db: Session = Depends(get_db)) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True), Product.stock_qty <= Product.min_stock)
        .order_by(Product.stock_qty.asc(), Product.name.asc())
    )
    return list(db.scalars(stmt).all())


@app.get("/inventory/movements", response_model=list[InventoryMovementOut])
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


@app.post("/inventory/adjust", response_model=InventoryMovementOut)
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


@app.get("/orders", response_model=list[OrderSummaryOut])
def list_orders(
    limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)
) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@app.post("/checkout", response_model=CheckoutResponse, status_code=201)
def checkout(payload: CheckoutRequest, db: Session = Depends(get_db)) -> CheckoutResponse:
    requested_qty: dict[int, int] = {}
    for item in payload.items:
        requested_qty[item.product_id] = requested_qty.get(item.product_id, 0) + item.quantity

    product_ids = list(requested_qty.keys())
    stmt = select(Product).where(Product.id.in_(product_ids), Product.is_active.is_(True))
    products = list(db.scalars(stmt).all())
    product_map = {product.id: product for product in products}

    missing_ids = [product_id for product_id in product_ids if product_id not in product_map]
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


@app.get("/bookkeeping/ledger", response_model=list[LedgerEntryOut])
def list_ledger(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[LedgerEntry]:
    stmt = select(LedgerEntry)
    if start_date:
        stmt = stmt.where(LedgerEntry.tx_date >= day_start(start_date))
    if end_date:
        stmt = stmt.where(LedgerEntry.tx_date <= day_end(end_date))
    stmt = stmt.order_by(LedgerEntry.tx_date.desc(), LedgerEntry.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


@app.get("/bookkeeping/trial-balance", response_model=list[TrialBalanceItem])
def trial_balance(
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> list[TrialBalanceItem]:
    debit_expr = func.coalesce(
        func.sum(case((LedgerEntry.direction == "debit", LedgerEntry.amount), else_=0)),
        0,
    )
    credit_expr = func.coalesce(
        func.sum(case((LedgerEntry.direction == "credit", LedgerEntry.amount), else_=0)),
        0,
    )

    stmt = select(
        LedgerEntry.account,
        debit_expr.label("debit"),
        credit_expr.label("credit"),
    ).group_by(LedgerEntry.account)

    if start_date:
        stmt = stmt.where(LedgerEntry.tx_date >= day_start(start_date))
    if end_date:
        stmt = stmt.where(LedgerEntry.tx_date <= day_end(end_date))

    stmt = stmt.order_by(LedgerEntry.account.asc())
    rows = db.execute(stmt).all()

    result: list[TrialBalanceItem] = []
    for account, debit, credit in rows:
        debit_value = to_money(debit)
        credit_value = to_money(credit)
        balance = to_money(debit_value - credit_value)
        result.append(
            TrialBalanceItem(
                account=account,
                debit=debit_value,
                credit=credit_value,
                balance=balance,
            )
        )
    return result


@app.get("/analytics/sales-summary", response_model=SalesSummaryOut)
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

    subtotal_value = to_money(subtotal)
    discount_value = to_money(discount)
    tax_value = to_money(tax)
    revenue_value = to_money(revenue)
    cogs_value = to_money(cogs)
    avg_order_value = to_money(revenue_value / order_count) if order_count else Decimal("0.00")
    gross_profit = to_money(revenue_value - cogs_value)

    return SalesSummaryOut(
        order_count=order_count,
        subtotal=subtotal_value,
        discount=discount_value,
        tax=tax_value,
        revenue=revenue_value,
        items_sold=int(items_sold or 0),
        cogs=cogs_value,
        gross_profit=gross_profit,
        avg_order_value=avg_order_value,
    )


@app.get("/analytics/top-products", response_model=list[TopProductOut])
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
    rows = db.execute(stmt).all()

    return [
        TopProductOut(
            product_id=product_id,
            product_name=product_name,
            qty_sold=int(qty_sold or 0),
            revenue=to_money(revenue),
        )
        for product_id, product_name, qty_sold, revenue in rows
    ]


@app.get("/analytics/stock-valuation", response_model=StockValuationOut)
def stock_valuation(db: Session = Depends(get_db)) -> StockValuationOut:
    products = list(db.scalars(select(Product).where(Product.is_active.is_(True))).all())
    total_units = sum(product.stock_qty for product in products)

    inventory_cost_value = Decimal("0.00")
    inventory_retail_value = Decimal("0.00")
    for product in products:
        inventory_cost_value += to_money(product.cost_price) * product.stock_qty
        inventory_retail_value += to_money(product.sell_price) * product.stock_qty

    inventory_cost_value = to_money(inventory_cost_value)
    inventory_retail_value = to_money(inventory_retail_value)
    potential_margin = to_money(inventory_retail_value - inventory_cost_value)

    return StockValuationOut(
        active_products=len(products),
        total_units=total_units,
        inventory_cost_value=inventory_cost_value,
        inventory_retail_value=inventory_retail_value,
        potential_margin=potential_margin,
    )
