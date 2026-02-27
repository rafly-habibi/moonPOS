from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP

MONEY_STEP = Decimal("0.01")


def to_money(value: Decimal | int | float | None) -> Decimal:
    if value is None:
        value = Decimal("0.00")
    return Decimal(str(value)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min)


def day_end(day: date) -> datetime:
    return datetime.combine(day, time.max)
