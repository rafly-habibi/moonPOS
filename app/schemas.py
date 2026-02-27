from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    sell_price: Decimal = Field(gt=0)
    cost_price: Decimal = Field(ge=0)
    stock_qty: int = Field(default=0, ge=0)
    min_stock: int = Field(default=5, ge=0)

    @field_validator("sku", "name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field tidak boleh kosong.")
        return cleaned

    @field_validator("category")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned if cleaned else None


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    category: str | None
    sell_price: Decimal
    cost_price: Decimal
    stock_qty: int
    min_stock: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CheckoutItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class CheckoutRequest(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1)
    discount: Decimal = Field(default=Decimal("0.00"), ge=0)
    tax: Decimal = Field(default=Decimal("0.00"), ge=0)
    payment_method: str = Field(default="cash", min_length=1, max_length=40)

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("payment_method tidak boleh kosong.")
        return cleaned


class OrderItemOut(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class CheckoutResponse(BaseModel):
    order_id: int
    order_number: str
    created_at: datetime
    payment_method: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    cogs: Decimal
    gross_profit: Decimal
    items: list[OrderItemOut]


class OrderSummaryOut(BaseModel):
    id: int
    order_number: str
    created_at: datetime
    payment_method: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal

    model_config = ConfigDict(from_attributes=True)


class InventoryAdjustmentRequest(BaseModel):
    product_id: int = Field(gt=0)
    quantity_change: int
    reason: str | None = None
    counterparty_account: str | None = None

    @field_validator("quantity_change")
    @classmethod
    def validate_non_zero_quantity(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity_change tidak boleh 0.")
        return value


class InventoryMovementOut(BaseModel):
    id: int
    product_id: int
    movement_type: str
    quantity_change: int
    before_qty: int
    after_qty: int
    reason: str | None
    ref_type: str | None
    ref_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LedgerEntryOut(BaseModel):
    id: int
    tx_ref: str
    tx_date: datetime
    account: str
    direction: str
    amount: Decimal
    note: str | None

    model_config = ConfigDict(from_attributes=True)


class TrialBalanceItem(BaseModel):
    account: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class SalesSummaryOut(BaseModel):
    order_count: int
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    revenue: Decimal
    items_sold: int
    cogs: Decimal
    gross_profit: Decimal
    avg_order_value: Decimal


class TopProductOut(BaseModel):
    product_id: int
    product_name: str
    qty_sold: int
    revenue: Decimal


class StockValuationOut(BaseModel):
    active_products: int
    total_units: int
    inventory_cost_value: Decimal
    inventory_retail_value: Decimal
    potential_margin: Decimal
