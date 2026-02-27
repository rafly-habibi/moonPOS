from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Product


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
