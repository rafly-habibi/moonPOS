from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import LedgerEntry
from ..utils import to_money


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
